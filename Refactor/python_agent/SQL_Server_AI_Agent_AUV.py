# -*- coding: utf-8 -*-
"""
Dr. Data — Clinical Agent v2 (LLM-orchestrated)

Flujo:
  1. LLM planificador decide qué tool del MCP llamar y con qué args
  2. Python ejecuta el tool
  3. LLM analizador recibe los datos y genera la respuesta en lenguaje natural

Sin reglas hardcodeadas de intención ni extractores de keywords.
"""

from __future__ import annotations

import os
import re
import io
import json
import base64
import subprocess
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
from dotenv import load_dotenv
import anyio

from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp import ClientSession

# =========================================================
# Config
# =========================================================
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

MCP_INIT_TIMEOUT = int(os.getenv("MCP_INIT_TIMEOUT", "60"))
MCP_TOOL_TIMEOUT = int(os.getenv("MCP_TOOL_TIMEOUT", "30"))
LLM_TIMEOUT      = int(os.getenv("LLM_TIMEOUT", "60"))
OVERALL_TIMEOUT  = int(os.getenv("OVERALL_TIMEOUT", "120"))
MAX_ROWS_TO_LLM  = int(os.getenv("MAX_ROWS_TO_LLM", "100"))

DEBUG_MCP    = os.getenv("DEBUG_MCP", "0").strip().lower() in ("1", "true", "yes")
MCP_LOG_FILE = os.getenv("MCP_LOG_FILE", "").strip()

# =========================================================
# Logging
# =========================================================
def _log(msg: str) -> None:
    if not DEBUG_MCP and not MCP_LOG_FILE:
        return
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    if DEBUG_MCP:
        print(line)
    if MCP_LOG_FILE:
        try:
            with open(MCP_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

# =========================================================
# LLM
# =========================================================
def _build_llm_clients():
    """
    Devuelve (thinker_client, thinker_model, answerer_client, answerer_model).

    LLM_THINKER — planificador: decide qué tool llamar y con qué args (solo JSON).
    LLM_ANSWERER   — analizador: genera respuesta en lenguaje natural.

    Si LLM_THINKER_BASE_URL / LLM_THINKER_MODEL no están definidos,
    el thinker reutiliza el mismo cliente que el answerer (sin costo extra).
    """
    from openai import OpenAI

    provider = os.getenv("LLM_PROVIDER", "openai_compat").strip().lower()

    if provider == "azure":
        from openai import AzureOpenAI
        client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview"),
            timeout=LLM_TIMEOUT,
        )
        model = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4")
        return client, model, client, model

    # Answerer — genera la respuesta final (modelo grande, Groq)
    answerer_client = OpenAI(
        api_key=os.getenv("LLM_ANSWERER_API_KEY", "dummy-key"),
        base_url=os.getenv("LLM_ANSWERER_BASE_URL", "http://localhost:11434/v1"),
        timeout=LLM_TIMEOUT,
    )
    answerer_model = os.getenv("LLM_ANSWERER_MODEL", "llama-3.3-70b-versatile")

    # Thinker — solo devuelve JSON con tool+args (puede ser modelo local pequeño)
    thinker_base_url = os.getenv("LLM_THINKER_BASE_URL", "").strip()
    thinker_model    = os.getenv("LLM_THINKER_MODEL", "").strip()

    if thinker_base_url and thinker_model:
        thinker_client = OpenAI(
            api_key="ollama",
            base_url=thinker_base_url,
            timeout=LLM_TIMEOUT,
        )
        _log(f"[LLM] thinker={thinker_model}@{thinker_base_url} | answerer={answerer_model}")
    else:
        thinker_client = answerer_client
        thinker_model  = answerer_model
        _log(f"[LLM] single model={answerer_model}")

    return thinker_client, thinker_model, answerer_client, answerer_model

# =========================================================
# Prompts
# =========================================================
PLANNER_SYSTEM = """\
Eres el planificador del sistema médico SGP. Devuelve SOLO JSON válido.
Formato: {{"tool":"nombre","args":{{}}}} o {{"tool":null,"args":{{}}}} si no aplica.
Hoy: {today}

═══ HERRAMIENTAS ═══
{tools_desc}

═══ ESQUEMA DE DATOS ═══
PACIENTES (patient_filter):
  persona.nombre, persona.apellidos, persona.ci, persona.sangre
  persona.sexo → valores exactos: Femenino | Masculino | Otro | (null=Sin género)
  persona.fecha_nacimiento → ISO: 2026-04-06T04:00:00.000000Z
  persona.ocupacion, persona.direccion, persona.telf1, persona.telf2
  estado → true=activo | false=inactivo

CITAS (citas_filter / citas_by_patient):
  hora_inicio, hora_fin → ISO: 2026-04-07T03:36:32.000000Z
  estado → "cerrada" | "en curso" | "pendiente" | "cancelada"
  tipo_evento → "Consulta" | "Control" | "Urgencia" | otros
  motivo, comentarios, patient_id

VISITAS (visitas_by_patient / visitas_by_cita):
  motivo, diagnostico, conducta, comentarios
  peso, altura, temperatura, f_cardiaca, f_respiratoria
  p_arterial_1, p_arterial_5
  patient_id, cita_id

PAGOS (payments_by_patient / payments_statistics / payments_list):
  monto, saldo, metodo → "Efectivo"|"Transferencia"|"Tarjeta"
  motivo, patient_id

OPERADORES de filtro: eq, neq, gt, gte, lt, lte, contains, startsWith, endsWith, in, exists

═══ REGLAS ═══
- Si la query menciona un nombre de paciente para citas/visitas/pagos → usa citas_by_patient/visitas_by_patient/payments_by_patient con patient_id=<nombre> (el sistema lo resolverá a ID automáticamente)
- Nunca uses patient_id con un nombre en citas_filter — usa citas_by_patient
- Para cumpleaños del mes/día: filtra persona.fecha_nacimiento con contains sobre el mes/día
- Para edad: calcula el año de nacimiento y usa gt/lt en persona.fecha_nacimiento
- Para pacientes inactivos: estado eq false
- filters SIEMPRE debe ser una lista de objetos: {{"filters":[{{"field":"campo","op":"operador","value":"valor"}}]}}
- Para "pacientes que empiezan con la letra M" usa patient_filter con field="persona.nombre", op="startsWith", value="M", limit=1000
- Nunca uses este formato: {{"filters":{{"persona.nombre":{{"contains":"M"}}}}}}
"""

# Tools curadas que el planificador ve — evita saturar con las 26
_PLANNER_TOOLS = {
    "patient_filter", "citas_filter", "citas_by_patient",
    "visitas_by_patient", "visitas_by_cita",
    "dashboard_stats", "payments_statistics", "payments_by_patient", "payments_list",
    "estudios_by_patient", "estudios_by_cita",
    "recetas_by_visita", "notas_by_cita", "archivos_by_patient",
    "antecedents_get", "clinic_bundle",
}

ANALYZER_SYSTEM = """\
Eres el asistente médico del sistema SGP. Responde en español, de forma breve y precisa.
Usa SOLO los datos proporcionados. No inventes ni asumas información.
Los datos ya vienen filtrados — el campo Total indica exactamente cuántos registros hay.
Nunca confundas un ID o número de paciente con una cantidad de visitas o registros.
Si los datos incluyen fechas de nacimiento y preguntan por edad o cumpleaños, calcúlalo tú mismo.\
"""

# =========================================================
# Utilidades
# =========================================================
def _local_today() -> str:
    return datetime.now(ZoneInfo("America/La_Paz")).strftime("%Y-%m-%d")

def _extract_json(text: str) -> Optional[dict]:
    """Extrae el primer JSON válido del texto — tolerante a respuestas imperfectas del LLM."""
    # bloque ```json ... ```
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # { ... } directo
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    return None

def _flatten_patient_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Aplana un objeto paciente extrayendo campos de persona."""
    persona = row.get("persona") or {}
    nombre = " ".join(filter(None, [persona.get("nombre"), persona.get("apellidos")])) or None
    return {
        "id": row.get("id") or row.get("patient_id"),
        "nombre": nombre,
        "ci": persona.get("ci"),
        "sexo": persona.get("sexo") or "Sin género",
        "telefono": persona.get("telf1") or persona.get("telf2"),
        "fecha_nacimiento": (persona.get("fecha_nacimiento") or "")[:10] or None,
        "estado": row.get("estado"),
    }

def _rows_to_excel_b64(rows: List[Dict[str, Any]], sheet_name: str = "Resultados") -> Optional[str]:
    if not rows:
        return None
    try:
        buf = io.BytesIO()
        pd.DataFrame(rows).to_excel(buf, index=False, sheet_name=sheet_name, engine="openpyxl")
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        return None

def _unwrap_rows(payload: Any) -> List[Dict[str, Any]]:
    """Extrae lista de rows de cualquier estructura que devuelva el MCP."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("items", "rows", "data", "results"):
            v = payload.get(k)
            if isinstance(v, list):
                return v
    return []

def _normalize_tool_args(args: Any, question: str = "") -> Dict[str, Any]:
    """Corrige formatos comunes que devuelve el planner antes de llamar al MCP."""
    if not isinstance(args, dict):
        return {}

    normalized = dict(args)

    filters = normalized.get("filters")
    if isinstance(filters, dict):
        if all(k in filters for k in ("field", "op", "value")):
            normalized["filters"] = [filters]
        else:
            converted_filters = []
            for field, op_map in filters.items():
                if isinstance(op_map, dict):
                    for op, value in op_map.items():
                        converted_filters.append({"field": field, "op": op, "value": value})
                else:
                    converted_filters.append({"field": field, "op": "eq", "value": op_map})
            normalized["filters"] = converted_filters
    elif filters is None and isinstance(normalized.get("filter"), dict):
        normalized["filters"] = [normalized.pop("filter")]

    if "filters" not in normalized and all(k in normalized for k in ("field", "op", "value")):
        normalized["filters"] = [{
            "field": normalized.pop("field"),
            "op": normalized.pop("op"),
            "value": normalized.pop("value"),
        }]

    op_aliases = {
        "startswith": "startsWith",
        "starts_with": "startsWith",
        "starts-with": "startsWith",
        "endswith": "endsWith",
        "ends_with": "endsWith",
        "ends-with": "endsWith",
    }
    for f in normalized.get("filters", []) or []:
        if isinstance(f, dict) and isinstance(f.get("op"), str):
            key = f["op"].strip()
            f["op"] = op_aliases.get(key.lower(), key)
            q = question.lower()
            asks_prefix = any(word in q for word in ("empiec", "comien", "inici", "arranc"))
            if asks_prefix and f["op"] == "contains" and f.get("field") in ("persona.nombre", "persona.apellidos", "nombre", "apellidos"):
                f["op"] = "startsWith"

    return normalized

def _diagnose_node_sync(cmd: List[str], env: dict, cwd: Optional[str], seconds: int = 5):
    _log("---- DIAG: spawning node process ----")
    try:
        proc = subprocess.Popen(
            cmd, cwd=cwd, env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
        )
        try:
            proc.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            proc.terminate()
        _, err = proc.communicate(timeout=2)
        if (err or "").strip():
            _log(f"DIAG STDERR: {err[:2000]}")
        _log(f"DIAG returncode={proc.returncode}")
    except Exception as e:
        _log(f"DIAG failed: {repr(e)}")

# =========================================================
# MCP Proxy
# =========================================================
class NodeMCPToolsProxy:
    def __init__(self, session: ClientSession):
        self.session = session
        self.allowed_tools: Set[str] = set()
        self.tools_meta: List[Dict] = []

    async def refresh_allowed_tools(self) -> None:
        try:
            with anyio.fail_after(MCP_TOOL_TIMEOUT):
                resp = await self.session.list_tools()
            raw = getattr(resp, "tools", None) or resp
            if isinstance(raw, list):
                for t in raw:
                    name = getattr(t, "name", None) or (t.get("name") if isinstance(t, dict) else None)
                    desc = getattr(t, "description", "") or (t.get("description", "") if isinstance(t, dict) else "")
                    if name:
                        self.allowed_tools.add(str(name))
                        self.tools_meta.append({"name": str(name), "description": str(desc)})
            _log(f"[TOOLS] loaded {len(self.allowed_tools)} tools")
        except Exception as e:
            _log(f"[TOOLS] list_tools failed: {repr(e)}")
            self.allowed_tools = {
                "patient_list", "patient_get", "patient_filter",
                "citas_list", "citas_filter", "citas_by_patient",
                "visitas_by_patient", "visitas_by_cita",
                "antecedents_get", "antecedents_filter",
                "payments_list", "payments_statistics",
                "estudios_by_patient", "dashboard_stats",
                "clinic_bundle",
            }

    def tools_description(self) -> str:
        if self.tools_meta:
            return "\n".join(
                f"{t['name']}: {t['description']}"
                for t in self.tools_meta
                if t['name'] in _PLANNER_TOOLS
            )
        return "\n".join(f"{t}" for t in sorted(self.allowed_tools & _PLANNER_TOOLS))

    async def call(self, name: str, args: Optional[dict] = None) -> Any:
        if self.allowed_tools and name not in self.allowed_tools:
            raise RuntimeError(f"Tool '{name}' no existe en MCP.")
        _log(f"[TOOL] call {name} args={args or {}}")
        with anyio.fail_after(MCP_TOOL_TIMEOUT):
            res = await self.session.call_tool(name, args or {})

        content = getattr(res, "content", None) or res
        payload = None
        if isinstance(content, list) and content:
            txt = getattr(content[0], "text", None)
            if txt:
                try:
                    payload = json.loads(txt)
                except Exception:
                    payload = {"_raw": txt[:2000]}

        if isinstance(payload, dict) and "ok" in payload:
            if payload.get("ok") is True:
                return payload.get("data")
            raise RuntimeError(payload.get("error") or "MCP tool error")

        return payload if payload is not None else content

# =========================================================
# Agent
# =========================================================
class MedicalAgentMCP:
    def __init__(
        self,
        tools: NodeMCPToolsProxy,
        thinker_client, thinker_model: str,
        answerer_client,   answerer_model: str,
    ):
        self.tools          = tools
        self.thinker        = thinker_client
        self.thinker_model  = thinker_model
        self.answerer          = answerer_client
        self.answerer_model    = answerer_model

    def _call_llm(self, client, model: str, system: str, user: str,
                  temperature: float = 0, json_mode: bool = False) -> str:
        kwargs: Dict[str, Any] = dict(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            timeout=LLM_TIMEOUT,
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    def _plan(self, question: str) -> Dict[str, Any]:
        """Thinker: decide qué tool llamar y con qué args (devuelve JSON)."""
        today = _local_today()
        system = PLANNER_SYSTEM.format(
            tools_desc=self.tools.tools_description(),
            today=today,
        )
        raw = self._call_llm(self.thinker, self.thinker_model,
                             system, question, temperature=0, json_mode=True)
        _log(f"[THINKER] response: {raw[:300]}")
        plan = _extract_json(raw)
        if not plan:
            _log("[THINKER] failed to parse JSON")
            return {"tool": None, "args": {}}
        return plan

    def _analyze(self, question: str, rows: List[Dict], extra_context: str = "") -> str:
        """Asker: analiza los datos y genera respuesta en lenguaje natural."""
        if extra_context:
            user_msg = f"Q: {question}\nDatos: {extra_context}"
        else:
            total = len(rows)
            if total <= MAX_ROWS_TO_LLM:
                data_str = json.dumps(rows, ensure_ascii=False, default=str, separators=(',', ':'))
                user_msg = f"Q: {question}\nTotal:{total}\n{data_str}"
            else:
                sample = rows[:MAX_ROWS_TO_LLM]
                data_str = json.dumps(sample, ensure_ascii=False, default=str, separators=(',', ':'))
                user_msg = f"Q: {question}\nTotal:{total} (muestra de {MAX_ROWS_TO_LLM}):\n{data_str}"
        return self._call_llm(self.answerer, self.answerer_model,
                              ANALYZER_SYSTEM, user_msg, temperature=0)

    async def _resolve_patient_id(self, name: str) -> Optional[str]:
        """Busca un paciente por nombre/apellido y devuelve su ID numérico."""
        _log(f"[RESOLVE] buscando patient_id para nombre='{name}'")
        parts = name.strip().split()

        # Intentar con cada parte del nombre (nombre o apellido)
        for part in parts:
            if len(part) < 3:
                continue
            for field in ("persona.nombre", "persona.apellidos"):
                raw = await self.tools.call("patient_filter", {
                    "filters": [{"field": field, "op": "contains", "value": part}],
                    "limit": 10,
                })
                rows = _unwrap_rows(raw)
                if rows:
                    # si hay varios, intentar afinar con otra parte del nombre
                    if len(rows) > 1 and len(parts) > 1:
                        other_parts = [p for p in parts if p != part and len(p) >= 3]
                        for row in rows:
                            persona = row.get("persona", {})
                            full = f"{persona.get('nombre','')} {persona.get('apellidos','')}".lower()
                            if any(p.lower() in full for p in other_parts):
                                pid = row.get("id") or row.get("patient_id")
                                _log(f"[RESOLVE] encontrado id={pid} ({full})")
                                return str(pid) if pid is not None else None
                    pid = rows[0].get("id") or rows[0].get("patient_id")
                    _log(f"[RESOLVE] encontrado id={pid}")
                    return str(pid) if pid is not None else None
        return None

    async def query(self, question: str) -> Dict[str, Any]:
        # ── Paso 1: planificar ──────────────────────────────
        plan = self._plan(question)
        tool_name = plan.get("tool")
        args = _normalize_tool_args(plan.get("args") or {}, question)
        _log(f"[PLAN] tool={tool_name} args={args}")

        # sin tool — LLM responde directo
        if not tool_name or tool_name not in self.tools.allowed_tools:
            answer = self._call_llm(
                self.answerer,
                self.answerer_model,
                ANALYZER_SYSTEM,
                f"Pregunta: {question}\n\nNo hay datos disponibles del sistema para esta consulta.",
                temperature=0.3,
            )
            return {"answer": answer, "data": {"rows": [], "row_count": 0}, "steps": 1}

        # ── Paso 1b: resolver nombre → patient_id si hace falta ────
        # Si el tool necesita un patient_id pero el planificador puso un string no numérico
        _ID_ARGS = {"patient_id", "patientId"}
        for id_field in _ID_ARGS:
            val = args.get(id_field)
            if val and not str(val).isdigit():
                # es un nombre, no un ID — resolver
                resolved = await self._resolve_patient_id(str(val))
                if resolved:
                    args[id_field] = resolved
                    _log(f"[RESOLVE] {id_field} '{val}' → '{resolved}'")
                else:
                    return {
                        "answer": f"No encontré ningún paciente con el nombre '{val}'.",
                        "data": {"rows": [], "row_count": 0},
                        "steps": 2,
                    }

        # Si es citas_filter con patient_id como nombre en filters, resolver también
        if tool_name in ("citas_filter", "citas_by_patient", "visitas_by_patient",
                         "estudios_by_patient", "pagos_by_patient", "payments_by_patient"):
            for f in args.get("filters", []):
                if f.get("field") == "patient_id" and not str(f.get("value", "")).isdigit():
                    resolved = await self._resolve_patient_id(str(f["value"]))
                    if resolved:
                        f["value"] = resolved
                        _log(f"[RESOLVE] filter patient_id '{f['value']}' → '{resolved}'")

        # ── Paso 2: ejecutar tool ───────────────────────────
        try:
            raw = await self.tools.call(tool_name, args)
        except Exception as e:
            _log(f"[TOOL ERROR] {repr(e)}")
            return {
                "answer": f"Error al consultar el sistema: {e}",
                "data": {"rows": [], "row_count": 0},
                "steps": 1,
            }

        # ── Paso 3: normalizar rows ─────────────────────────
        rows = _unwrap_rows(raw)

        if tool_name in ("patient_filter", "patient_list", "patient_get"):
            rows = [_flatten_patient_row(r) for r in rows]

        # para tools que devuelven dict plano (stats, dashboard)
        extra_context = ""
        if not rows and isinstance(raw, dict):
            extra_context = json.dumps(raw, ensure_ascii=False, default=str)

        # ── Paso 4: LLM analiza ─────────────────────────────
        answer = self._analyze(question, rows, extra_context=extra_context)

        # La tabla refleja exactamente lo que devolvió el MCP.
        # Si el LLM dice "no hay" pero el MCP sí tiene datos, el LLM se equivocó —
        # en ese caso reemplazamos la respuesta con una automática basada en los datos reales.
        _NO_RESULT_PHRASES = ("no hay", "no existe", "no encontré", "no encontre",
                              "ningún", "ningun", "vacía", "vacia", "sin registros", "no se encontr")
        llm_says_empty = any(p in answer.lower() for p in _NO_RESULT_PHRASES)

        _TOOL_NOUN = {
            "patient_filter": "pacientes", "patient_list": "pacientes", "patient_get": "paciente",
            "citas_filter": "citas", "citas_list": "citas", "citas_by_patient": "citas",
            "visitas_by_patient": "visitas", "visitas_by_cita": "visitas",
            "payments_list": "pagos", "payments_by_patient": "pagos",
            "estudios_by_patient": "estudios", "estudios_by_cita": "estudios",
            "recetas_by_visita": "recetas", "notas_by_cita": "notas",
            "archivos_by_patient": "archivos", "antecedents_get": "antecedentes",
        }

        if llm_says_empty and rows:
            noun = _TOOL_NOUN.get(tool_name, "registros")
            answer = f"Encontré {len(rows)} {noun}."
            _log(f"[SYNC] LLM dijo vacío pero MCP devolvió {len(rows)} rows — respuesta corregida")

        # ── Paso 5: Excel ───────────────────────────────────
        sheet = tool_name.split("_")[0].capitalize()
        excel_b64 = _rows_to_excel_b64(rows, sheet_name=sheet) if rows else None
        excel_name = f"{tool_name.split('_')[0]}.xlsx" if excel_b64 else None

        return {
            "answer": answer,
            "data": {"rows": rows, "row_count": len(rows)},
            "steps": 2,
            "excel_bytes": excel_b64,
            "excel_name": excel_name,
        }

# =========================================================
# Bootstrap MCP Node
# =========================================================
async def ask_with_embedded_mcp(question: str) -> Dict[str, Any]:
    node_entry   = os.getenv("NODE_MCP_ENTRY", "").strip()
    api_base_url = os.getenv("API_BASE_URL", "").strip()
    node_cwd     = os.getenv("NODE_MCP_CWD", "").strip() or (os.path.dirname(node_entry) if node_entry else "")

    if not node_entry or not os.path.isfile(node_entry):
        return {"answer": "Falta NODE_MCP_ENTRY.", "data": {"rows": [], "row_count": 0}, "steps": 0}
    if not api_base_url:
        return {"answer": "Falta API_BASE_URL.", "data": {"rows": [], "row_count": 0}, "steps": 0}

    env = {
        **os.environ,
        "API_BASE_URL": api_base_url,
        "NODE_NO_WARNINGS": "1",
        "HTTP_TIMEOUT_MS": os.getenv("HTTP_TIMEOUT_MS", "25000"),
    }
    cmd = ["node", node_entry]
    server_params = StdioServerParameters(command=cmd[0], args=cmd[1:], env=env, cwd=node_cwd)
    _log(f"Starting MCP: {node_entry}")

    thinker_client, thinker_model, answerer_client, answerer_model = _build_llm_clients()

    try:
        with anyio.fail_after(OVERALL_TIMEOUT):
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    with anyio.fail_after(MCP_INIT_TIMEOUT):
                        await session.initialize()
                    _log("MCP initialize OK")

                    tools = NodeMCPToolsProxy(session)
                    await tools.refresh_allowed_tools()

                    agent = MedicalAgentMCP(
                        tools,
                        thinker_client, thinker_model,
                        answerer_client, answerer_model,
                    )
                    return await agent.query(question)

    except TimeoutError:
        _log(f"OVERALL timeout ({OVERALL_TIMEOUT}s)")
        _diagnose_node_sync(cmd, env, cwd=node_cwd)
        return {"answer": f"Timeout ({OVERALL_TIMEOUT}s).", "data": {"rows": [], "row_count": 0}, "steps": 0}
    except Exception as e:
        _log(f"MCP failed: {repr(e)}")
        _diagnose_node_sync(cmd, env, cwd=node_cwd)
        return {"answer": f"Error MCP: {e}", "data": {"rows": [], "row_count": 0}, "steps": 0}

# =========================================================
# Runner
# =========================================================
class Runner:
    def run(self, question: str) -> Dict[str, Any]:
        return anyio.run(ask_with_embedded_mcp, question)
