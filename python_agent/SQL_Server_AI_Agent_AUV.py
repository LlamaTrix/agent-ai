# -*- coding: utf-8 -*-
"""
Dr. Data — Clinical Agent (API REST) + MCP Node (stdio) — Python 3.11

✅ FIXES (patient_search + fallback cuando API ignora filtros):
- ✅ Si se pide filtro por sangre (antecedents.sangre) y patient_search no lo aplica,
  se hace fallback automático:
   1) antecedents_filter(sangre=...) -> patient_ids
   2) patient_search(patients.id IN ids) si soporta op "in"
   3) sino: patient_list y filtrado client-side por id
- ✅ Detecta “filtro ignorado” comparando resultados vs baseline (solo estado=1).
- ✅ Mantiene tus reglas de intención y fechas relativas.
"""

from __future__ import annotations

import os
import re
import io
import json
import hashlib
import unicodedata
import subprocess
from typing import List, Dict, Any, Optional, Tuple, Set
from datetime import datetime, timedelta
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

LOG_TOOL_RESPONSE = os.getenv("LOG_TOOL_RESPONSE", "0").strip().lower() in ("1", "true", "yes")
LOG_TOOL_RESPONSE_MAX_CHARS = int(os.getenv("LOG_TOOL_RESPONSE_MAX_CHARS", "4000"))
LOG_TOOL_RESPONSE_REDACT = os.getenv("LOG_TOOL_RESPONSE_REDACT", "1").strip().lower() in ("1", "true", "yes")

_REDACT_KEYS = {
    "ci", "carnet", "dni", "documento",
    "telf1", "telf2", "telefono", "celular",
    "email",
}

EXCEL_EXPORT_THRESHOLD = int(os.getenv("EXCEL_EXPORT_THRESHOLD", "50"))
EXCEL_EXPORT_MAX_ROWS = int(os.getenv("EXCEL_EXPORT_MAX_ROWS", "50000"))

DEBUG_MCP = os.getenv("DEBUG_MCP", "0").strip().lower() in ("1", "true", "yes")
MCP_LOG_FILE = os.getenv("MCP_LOG_FILE", "").strip()

MCP_INIT_TIMEOUT = int(os.getenv("MCP_INIT_TIMEOUT", "60"))
MCP_TOOL_TIMEOUT = int(os.getenv("MCP_TOOL_TIMEOUT", "30"))
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "35"))
OVERALL_TIMEOUT = int(os.getenv("OVERALL_TIMEOUT", "90"))

NATURALIZE_WITH_LLM = os.getenv("NATURALIZE_WITH_LLM", "1").strip().lower() in ("1", "true", "yes")
NATURALIZE_SAMPLE_ROWS = int(os.getenv("NATURALIZE_SAMPLE_ROWS", "10"))
NATURALIZE_MAX_CHARS = int(os.getenv("NATURALIZE_MAX_CHARS", "1200"))
MAX_TOOL_STEPS = int(os.getenv("MAX_TOOL_STEPS", "5"))

# =========================================================
# Logging
# =========================================================
def _log_mcp(msg: str) -> None:
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

def _safe_json_dumps(obj: Any, max_chars: int) -> str:
    try:
        s = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        s = str(obj)
    if len(s) > max_chars:
        return s[:max_chars] + "…(truncated)"
    return s

def _redact_pii(obj: Any) -> Any:
    if not LOG_TOOL_RESPONSE_REDACT:
        return obj
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if lk in _REDACT_KEYS:
                out[k] = "***"
            else:
                out[k] = _redact_pii(v)
        return out
    if isinstance(obj, list):
        return [_redact_pii(x) for x in obj[:200]]
    return obj

# =========================================================
# LLM
# =========================================================
def _build_llm_client():
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
    else:
        from openai import OpenAI
        client = OpenAI(
            api_key=os.getenv("LLAMA_API_KEY", "dummy-key"),
            base_url=os.getenv("LLAMA_BASE_URL", "http://localhost:11434/v1"),
            timeout=LLM_TIMEOUT,
        )
        model = os.getenv("LLAMA_MODEL", "llama3.2:1b")
    return client, model

# =========================================================
# Utilidades
# =========================================================
def _strip_accents_lc(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", (s or "").lower())
        if unicodedata.category(c) != "Mn"
    )

def _local_today() -> datetime:
    return datetime.now(ZoneInfo("America/La_Paz"))

def _is_count_request(q: str) -> bool:
    t = _strip_accents_lc(q or "")
    return any(p in t for p in ["cuantos", "cuántos", "cuanto", "total", "cantidad", "numero", "número", "conteo", "count"])

def _is_list_request(q: str) -> bool:
    t = _strip_accents_lc(q or "")
    return any(w in t for w in [
        "lista", "listame", "listado", "dame", "mostrar", "muéstrame", "muestrame",
        "ver", "traeme", "tráeme", "quiero ver", "devuelveme", "enseñame", "mostrarme", "mostrame", "devolveme"
    ])

def _diagnose_node_process_sync(cmd: List[str], env: Dict[str, str], cwd: Optional[str], seconds: int = 5):
    _log_mcp("---- DIAG: spawning node process (sync) ----")
    _log_mcp(f"DIAG CMD: {' '.join(cmd)}")
    _log_mcp(f"DIAG CWD: {cwd}")
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
        out, err = proc.communicate(timeout=2)
        if (out or "").strip():
            _log_mcp("DIAG STDOUT:")
            _log_mcp((out or "")[:4000])
        if (err or "").strip():
            _log_mcp("DIAG STDERR:")
            _log_mcp((err or "")[:4000])
        _log_mcp(f"DIAG returncode={proc.returncode}")
    except Exception as e:
        _log_mcp(f"DIAG failed: {repr(e)}")

# =========================================================
# Unwrap / payload
# =========================================================
def _unwrap_list(payload: Any) -> Any:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if isinstance(payload.get("data"), list):
            return payload["data"]
        d = payload.get("data")
        if isinstance(d, dict) and isinstance(d.get("data"), list):
            return d["data"]
        for k in ("items", "results", "rows"):
            v = payload.get(k)
            if isinstance(v, list):
                return v
        if isinstance(d, dict):
            for k in ("items", "results", "rows"):
                v = d.get(k)
                if isinstance(v, list):
                    return v
    return payload

def _extract_total_from_paginated(payload: Any) -> Optional[int]:
    if not isinstance(payload, dict):
        return None
    if "total" in payload:
        try:
            return int(payload.get("total"))
        except Exception:
            pass
    d = payload.get("data")
    if isinstance(d, dict) and "total" in d:
        try:
            return int(d.get("total"))
        except Exception:
            return None
    return None

def _to_rows_payload(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, list):
        return {"rows": payload, "row_count": len(payload)}
    if isinstance(payload, dict):
        for k in ("rows", "data", "items", "results"):
            v = payload.get(k)
            if isinstance(v, list):
                return {"rows": v, "row_count": len(v), "raw": payload}
        return {"rows": [], "row_count": 0, "raw": payload}
    return {"rows": [], "row_count": 0, "raw": payload}

def _pick_first(row: Dict[str, Any], keys: List[str]) -> Optional[str]:
    for k in keys:
        v = row.get(k)
        if v is not None and str(v).strip() != "":
            return str(v).strip()
    return None

def _format_patient_line(row: Dict[str, Any]) -> str:
    pid = _pick_first(row, ["patient_id", "patients_id", "id", "patientId"])
    persona = row.get("persona", {}) if isinstance(row.get("persona"), dict) else {}
    ci  = _pick_first(persona, ["ci", "carnet", "dni", "documento"]) or _pick_first(row, ["ci", "carnet", "dni", "documento", "persons_ci", "person_ci"])
    nombre = _pick_first(persona, ["nombre", "nombres", "first_name", "firstname"]) or _pick_first(row, ["nombre", "nombres", "first_name", "firstname"])
    apellidos = _pick_first(persona, ["apellidos", "paterno", "materno", "last_name", "lastname"]) or _pick_first(row, ["apellidos", "paterno", "materno", "last_name", "lastname"])
    full = " ".join([x for x in [nombre, apellidos] if x]) or _pick_first(row, ["full_name", "nombre_completo"])
    bits = []
    if pid: bits.append(f"ID:{pid}")
    if full: bits.append(full)
    if ci: bits.append(f"CI:{ci}")
    return " — ".join(bits) if bits else json.dumps(row, ensure_ascii=False, default=str)[:120]

def _render_patients_list(rows: List[Dict[str, Any]], total: int, limit: int = 20) -> str:
    shown = rows[:limit]
    lines = "\n".join([f"{i+1}. {_format_patient_line(r)}" for i, r in enumerate(shown)])
    if total > limit:
        return f"Encontré {total} pacientes. Mostrando {limit}:\n{lines}\n…(+{total - limit} más)"
    return f"Encontré {total} pacientes:\n{lines}"

def _fingerprint_patient_ids(rows: List[Dict[str, Any]], n: int = 10) -> Tuple[str, ...]:
    """
    Huella simple para detectar “mismo top 20”: si los primeros ids no cambian, el filtro fue ignorado.
    """
    out: List[str] = []
    for r in (rows or [])[:n]:
        if isinstance(r, dict):
            pid = r.get("patient_id") or r.get("patients_id") or r.get("id")
            if pid is not None:
                out.append(str(pid))
    return tuple(out)

# =========================================================
# Extractores (sexo/ci/sangre/fechas)
# =========================================================
_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

_MONTHS_ES = {
    "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
    "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
    "septiembre": "09", "setiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12",
}
_DAY_MONTH_ES_RE = re.compile(
    r"\b(\d{1,2})\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\b",
    re.IGNORECASE
)

def _extract_spanish_day_month(question: str) -> Optional[str]:
    q = question or ""
    m = _DAY_MONTH_ES_RE.search(q)
    if not m:
        return None
    day = int(m.group(1))
    mon_name = _strip_accents_lc(m.group(2))
    mm = _MONTHS_ES.get(mon_name)
    if not mm:
        return None
    yyyy = _local_today().year
    return f"{yyyy}-{mm}-{day:02d}"

def _extract_relative_date(question: str) -> Optional[str]:
    t = _strip_accents_lc(question or "")
    base = _local_today().date()
    if re.search(r"\bpasado\s+manana\b", t):
        return (base + timedelta(days=2)).strftime("%Y-%m-%d")
    if re.search(r"\bmanana\b", t):
        return (base + timedelta(days=1)).strftime("%Y-%m-%d")
    if re.search(r"\bhoy\b", t):
        return base.strftime("%Y-%m-%d")
    if re.search(r"\banteayer\b", t):
        return (base - timedelta(days=2)).strftime("%Y-%m-%d")
    if re.search(r"\bayer\b", t):
        return (base - timedelta(days=1)).strftime("%Y-%m-%d")
    return None

def _extract_date_exact_or_range(question: str) -> Optional[Tuple[str, str]]:
    q = question or ""
    dates = _DATE_RE.findall(q)
    if len(dates) >= 2:
        d1, d2 = dates[0], dates[1]
        return f"{d1} 00:00:00", f"{d2} 23:59:59"
    if len(dates) == 1:
        d = dates[0]
        return f"{d} 00:00:00", f"{d} 23:59:59"
    d_es = _extract_spanish_day_month(q)
    if d_es:
        return f"{d_es} 00:00:00", f"{d_es} 23:59:59"
    d_rel = _extract_relative_date(q)
    if d_rel:
        return f"{d_rel} 00:00:00", f"{d_rel} 23:59:59"
    return None

def _extract_sexo(question: str) -> Optional[str]:
    t = _strip_accents_lc(question or "")
    if re.search(r"\b(f|femenino|femeninas|mujer|mujeres)\b", t):
        return "femenino"
    if re.search(r"\b(m|masculino|masculinos|hombre|hombres|varon|varones)\b", t):
        return "masculino"
    return None

def _extract_ci_like(question: str) -> Optional[str]:
    q = question or ""
    m = re.search(r"\b(ci|carnet|dni|documento)\b[^0-9]{0,10}(\d{3,12})\b", q, flags=re.IGNORECASE)
    return m.group(2) if m else None

def _extract_blood_type(question: str) -> Optional[str]:
    qlc = _strip_accents_lc(question or "")
    m = re.search(r"(?i)\b(AB|A|B|O)\s*([+-])(?=$|\s|[.,;:!?])", question or "")
    if m:
        return f"{m.group(1).upper()}{m.group(2)}"
    m2 = re.search(r"\b(ab|a|b|o)\s*(positivo|negativo)\b", qlc)
    if m2:
        grp = m2.group(1).upper()
        sign = "+" if m2.group(2) == "positivo" else "-"
        return f"{grp}{sign}"
    return None

def _extract_nombre(question: str) -> Optional[str]:
    """Extrae un nombre propio de la pregunta eliminando palabras clave del sistema."""
    _STOP = {
        "paciente", "pacientes", "cita", "citas", "visita", "visitas",
        "lista", "listame", "listado", "dame", "mostrar", "muéstrame", "muestrame",
        "ver", "traeme", "tráeme", "buscar", "busca", "busco", "encontrar",
        "cuantos", "cuántos", "total", "hay", "el", "la", "los", "las",
        "de", "del", "con", "para", "que", "como", "quien", "quién",
        "un", "una", "unos", "unas", "en", "al", "se", "datos", "informacion",
        "información", "nombre", "apellido", "llamado", "llama", "apellidos",
        "mujer", "mujeres", "hombre", "hombres", "masculino", "femenino",
        "varon", "varones", "mayor", "mayores", "menor", "menores",
        "anos", "edad", "sangre", "tipo", "sangre",
    }
    tokens = re.findall(r"[a-záéíóúüñ]+", _strip_accents_lc(question or ""), re.IGNORECASE)
    # quedarse con tokens que no son stopwords y tienen más de 2 letras
    candidates = [t for t in tokens if t not in _STOP and len(t) > 2]
    if candidates:
        return candidates[0]  # tomar el primer candidato (nombre más probable)
    return None

def _extract_age_comparator(question: str) -> Optional[Tuple[str, int]]:
    q = _strip_accents_lc(question or "")
    m = re.search(r"\bmayor(?:es)?\s*(?:a|de)\s*(\d{1,3})\b", q)
    if m:
        return (">", int(m.group(1)))
    m2 = re.search(r"\bmenor(?:es)?\s*(?:a|de)\s*(\d{1,3})\b", q)
    if m2:
        return ("<", int(m2.group(1)))
    return None

def _is_patients_intent(q: str) -> bool:
    t = _strip_accents_lc(q or "")
    return any(w in t for w in ["paciente", "pacientes", "tabla de paciente", "tablas de paciente"])

def _is_citas_intent(q: str) -> bool:
    t = _strip_accents_lc(q or "")
    return any(w in t for w in ["cita", "citas", "agenda", "agendada", "agendadas", "turno", "turnos", "consulta", "consultas"])

def _is_pagos_intent(q: str) -> bool:
    t = _strip_accents_lc(q or "")
    return any(w in t for w in ["pago", "pagos", "cobro", "cobros", "monto", "estadistica", "estadísticas", "ingreso", "ingresos"])

def _is_visitas_intent(q: str) -> bool:
    t = _strip_accents_lc(q or "")
    return any(w in t for w in ["visita", "visitas", "historial", "atencion", "atención"])

def _is_estudios_intent(q: str) -> bool:
    t = _strip_accents_lc(q or "")
    return any(w in t for w in ["estudio", "estudios", "laboratorio", "laboratorios", "gabinete", "cardiolog"])

def _is_dashboard_intent(q: str) -> bool:
    t = _strip_accents_lc(q or "")
    return any(w in t for w in ["dashboard", "estadistica", "estadísticas", "resumen", "general", "total general"])

def _extract_total_from_filter_tool(payload: Any) -> Optional[int]:
    if isinstance(payload, dict):
        if "total" in payload:
            try:
                return int(payload.get("total") or 0)
            except Exception:
                pass
        items = payload.get("items")
        if isinstance(items, list):
            return len(items)
    return None

# =========================================================
# MCP Proxy + Aliases
# =========================================================
DEFAULT_TOOL_ALIASES: Dict[str, str] = {
    "list_people": "person_list",
    "get_person": "person_get",
    "list_patients": "patient_list",
    "get_patient": "patient_get",
    "list_citas": "citas_list",
    "citas_by_patient_id": "citas_by_patient",
    "list_visitas": "visitas_by_patient",
    "patients_search": "patient_search",
    "search_patients": "patient_search",
}

class NodeMCPToolsProxy:
    def __init__(self, session: ClientSession, aliases: Optional[Dict[str, str]] = None):
        self.session = session
        self.allowed_tools: Set[str] = set()
        self.aliases = aliases or dict(DEFAULT_TOOL_ALIASES)

    async def refresh_allowed_tools(self) -> None:
        tools: List[str] = []
        try:
            if hasattr(self.session, "list_tools"):
                with anyio.fail_after(MCP_TOOL_TIMEOUT):
                    resp = await self.session.list_tools()  # type: ignore[attr-defined]
                raw = getattr(resp, "tools", None) or resp
                if isinstance(raw, list):
                    for t in raw:
                        name = getattr(t, "name", None) or (t.get("name") if isinstance(t, dict) else None)
                        if name:
                            tools.append(str(name))
            _log_mcp(f"[TOOLS] session.list_tools found: {len(tools)} tools")
        except Exception as e:
            _log_mcp(f"[TOOLS] session.list_tools failed: {repr(e)}")

        if tools:
            self.allowed_tools = set(tools)
            _log_mcp(f"[TOOLS] allowed_tools loaded from server: {len(self.allowed_tools)}")
            return

        self.allowed_tools = {
            "person_list","person_get",
            "patient_list","patient_get","patient_search","patient_filter",
            "citas_list","citas_by_patient","citas_filter",
            "visitas_by_patient","visitas_by_cita",
            "antecedents_get","antecedents_filter",
            "payments_list","payments_by_patient","payments_statistics",
            "estudios_by_patient","estudios_by_cita",
            "recetas_by_visita",
            "dashboard_stats",
        }
        _log_mcp(f"[TOOLS] using hardcoded list: {len(self.allowed_tools)} tools")

    def _normalize_tool_name(self, name: str) -> str:
        name = (name or "").strip()
        return self.aliases.get(name, name)

    async def call_raw(self, name: str, args: Optional[dict] = None) -> Any:
        _log_mcp(f"[TOOL] start {name} args={args or {}}")
        with anyio.fail_after(MCP_TOOL_TIMEOUT):
            res = await self.session.call_tool(name, args or {})

        content = getattr(res, "content", None) or getattr(res, "contents", None) or res

        payload = None
        if isinstance(content, list) and content:
            item = content[0]
            txt = getattr(item, "text", None)
            if txt:
                try:
                    payload = json.loads(txt)
                except Exception:
                    payload = {"_raw_text": txt[:2000]}

        if isinstance(payload, dict) and "ok" in payload:
            if payload.get("ok") is True:
                data_out = payload.get("data")
                _log_mcp(f"[TOOL] done {name} ok")
                if LOG_TOOL_RESPONSE:
                    safe = _redact_pii(data_out)
                    _log_mcp(f"[TOOL] result {name}: {_safe_json_dumps(safe, LOG_TOOL_RESPONSE_MAX_CHARS)}")
                return data_out
            err_msg = payload.get("error") or payload.get("message") or "MCP tool error"
            _log_mcp(f"[TOOL] done {name} error={err_msg}")
            raise RuntimeError(err_msg)

        _log_mcp(f"[TOOL] done {name} (raw)")
        return payload if payload is not None else content

    async def call(self, name: str, args: Optional[dict] = None) -> Any:
        original = name
        name = self._normalize_tool_name(name)
        if self.allowed_tools and name not in self.allowed_tools:
            raise RuntimeError(f"Tool '{original}' no existe en MCP. Normalizada='{name}'.")
        return await self.call_raw(name, args)

# =========================================================
# Agent
# =========================================================
class MedicalAgentMCP:
    def __init__(self, tools: NodeMCPToolsProxy):
        self.tools = tools

    async def _patients_by_blood_fallback(self, blood: str, want_count: bool) -> Optional[Dict[str, Any]]:
        """
        Fallback porque patient_search está ignorando antecedents.sangre:
        1) antecedents_filter(sangre=blood) -> patient_ids
        2) patient_search(patients.id in ids) si soporta
        3) patient_list + filtro client-side
        """
        if "antecedents_filter" not in self.tools.allowed_tools:
            return None

        _log_mcp(f"[FALLBACK] antecedents_filter sangre={blood}")

        ares = await self.tools.call("antecedents_filter", {
            "filters": [{"field": "sangre", "op": "eq", "value": blood}],
            "page": 1,
            "pageSize": 1000,
        })

        items = []
        if isinstance(ares, dict) and isinstance(ares.get("items"), list):
            items = ares["items"]

        patient_ids: Set[Any] = set()
        for it in items:
            if isinstance(it, dict):
                pid = it.get("patient_id") or it.get("patients_id") or it.get("patientId")
                if pid is not None:
                    patient_ids.add(pid)

        if not patient_ids:
            payload = {"rows": [], "row_count": 0, "raw": {"antecedents_filter": ares}}
            return {"answer": f"No se encontraron pacientes con sangre {blood}.", "data": payload, "steps": 2}

        # intentar patient_search con IN
        if "patient_search" in self.tools.allowed_tools:
            try:
                res = await self.tools.call("patient_search", {
                    "filters": [
                        {"field": "patients.id", "op": "in", "value": sorted(list(patient_ids))},
                    ],
                    "per_page": 20 if not want_count else 1,
                    "flat": (not want_count),
                    "sort_by": "patients.id",
                    "sort_dir": "desc",
                })

                if want_count:
                    total = _extract_total_from_paginated(res)
                    if total is None:
                        rows = _unwrap_list(res)
                        payload = _to_rows_payload(rows)
                        return {"answer": f"Total: {payload['row_count']}.", "data": payload, "steps": 3}
                    return {"answer": f"Total: {total}.", "data": {"rows": [], "row_count": total, "raw": {"antecedents_filter": ares, "patient_search": res}}, "steps": 3}

                rows = _unwrap_list(res)
                payload = _to_rows_payload(rows)
                total = payload.get("row_count", 0)
                answer = _render_patients_list(payload["rows"], total=total, limit=20) if total else f"No se encontraron pacientes con sangre {blood}."
                return {"answer": answer, "data": payload, "steps": 3}

            except Exception as e:
                _log_mcp(f"[FALLBACK] patient_search IN failed: {e}")

        # último recurso: patient_list + filtro client-side
        if "patient_list" not in self.tools.allowed_tools:
            payload = {"rows": [], "row_count": len(patient_ids), "raw": {"antecedents_filter": ares}}
            return {"answer": f"Encontré {len(patient_ids)} pacientes con sangre {blood}, pero no pude listar detalles.", "data": payload, "steps": 3}

        pres = await self.tools.call("patient_list", {})
        prow = _unwrap_list(pres)
        rows: List[Dict[str, Any]] = []
        if isinstance(prow, list):
            for r in prow:
                if isinstance(r, dict):
                    pid = r.get("id") or r.get("patient_id") or r.get("patients_id")
                    if pid in patient_ids:
                        rows.append(r)

        payload = _to_rows_payload(rows)
        if want_count:
            return {"answer": f"Total: {payload['row_count']}.", "data": payload, "steps": 4}

        total = payload.get("row_count", 0)
        answer = _render_patients_list(payload["rows"], total=total, limit=20) if total else f"No se encontraron pacientes con sangre {blood}."
        return {"answer": answer, "data": payload, "steps": 4}

    async def _patients_via_patient_search(self, question: str, want_count: bool) -> Optional[Dict[str, Any]]:
        if "patient_filter" not in self.tools.allowed_tools:
            return None

        filters: List[Dict[str, Any]] = []

        sexo = _extract_sexo(question)
        if sexo:
            filters.append({"field": "persona.sexo", "op": "eq", "value": sexo})

        age_cmp = _extract_age_comparator(question)
        if age_cmp:
            op_sym, n = age_cmp
            filters.append({"field": "antecedents.edad", "op": "gt" if op_sym == ">" else "lt", "value": n})

        blood = _extract_blood_type(question)
        if blood:
            # lo mandamos como tú lo venías haciendo
            filters.append({"field": "persona.sangre", "op": "eq", "value": blood})

        ci_like = _extract_ci_like(question)
        if ci_like:
            filters.append({"field": "persona.ci", "op": "contains", "value": str(ci_like)})

        nombre_like = _extract_nombre(question)
        if nombre_like:
            filters.append({"field": "persona.nombre", "op": "contains", "value": nombre_like})

        dr = _extract_date_exact_or_range(question)
        if dr:
            filters.append({"field": "citas.hora_inicio", "op": "gte", "value": dr[0]})
            filters.append({"field": "citas.hora_inicio", "op": "lte", "value": dr[1]})

        # consulta real (con filtros)
        if want_count:
            res = await self.tools.call("patient_filter", {
                "filters": filters,
                "limit": 1000,  # limitar para count aproximado
            })
            rows = _unwrap_list(res)
            total = len(rows)
            payload = _to_rows_payload(rows)
            return {"answer": f"Total aproximado: {total} (limitado a 1000).", "data": payload, "steps": 2}

        res = await self.tools.call("patient_filter", {
            "filters": filters,
            "limit": 20,
            "sort": {"field": "id", "direction": "desc"},
        })
        rows = _unwrap_list(res)
        payload = _to_rows_payload(rows)
        total = payload.get("row_count", 0)
        if total <= 0:
            return {"answer": "No se encontraron pacientes.", "data": payload, "steps": 2}

        answer = _render_patients_list(payload["rows"], total=total, limit=20)
        return {"answer": answer, "data": payload, "steps": 2}

    async def _pagos(self, question: str, want_count: bool) -> Optional[Dict[str, Any]]:
        q = _strip_accents_lc(question)
        # estadísticas generales de pagos
        if any(w in q for w in ["estadistica", "estadísticas", "resumen", "total"]):
            if "payments_statistics" in self.tools.allowed_tools:
                res = await self.tools.call("payments_statistics")
                if isinstance(res, dict):
                    day   = res.get("day", 0)
                    month = res.get("mont", 0)
                    year  = res.get("year", 0)
                    total = res.get("total", 0)
                    answer = (
                        f"Estadísticas de pagos:\n"
                        f"- Hoy: Bs. {day}\n"
                        f"- Este mes: Bs. {month}\n"
                        f"- Este año: Bs. {year}\n"
                        f"- Total histórico: Bs. {total}"
                    )
                    return {"answer": answer, "data": {"rows": [], "row_count": 0, "raw": res}, "steps": 1}
        # lista de pagos
        if "payments_list" in self.tools.allowed_tools:
            res = await self.tools.call("payments_list")
            rows = res.get("data", []) if isinstance(res, dict) else []
            payload = _to_rows_payload(rows)
            total = payload.get("row_count", 0)
            if want_count:
                return {"answer": f"Total de pagos registrados: {total}.", "data": payload, "steps": 1}
            return {"answer": f"Encontré {total} pagos registrados.", "data": payload, "steps": 1}
        return None

    async def _visitas(self, question: str, want_count: bool) -> Optional[Dict[str, Any]]:
        if "visitas_by_patient" not in self.tools.allowed_tools:
            return None
        # extraer patient_id de la pregunta si menciona un número
        m = re.search(r"\b(\d+)\b", question)
        if m and "visitas_by_patient" in self.tools.allowed_tools:
            patient_id = int(m.group(1))
            res = await self.tools.call("visitas_by_patient", {"patient_id": patient_id})
            rows = res if isinstance(res, list) else []
            payload = _to_rows_payload(rows)
            total = payload.get("row_count", 0)
            return {"answer": f"Encontré {total} visitas para el paciente ID {patient_id}.", "data": payload, "steps": 1}
        return None

    async def _estudios(self, question: str, want_count: bool) -> Optional[Dict[str, Any]]:
        m = re.search(r"\b(\d+)\b", question)
        if m and "estudios_by_patient" in self.tools.allowed_tools:
            patient_id = int(m.group(1))
            res = await self.tools.call("estudios_by_patient", {"patient_id": patient_id})
            rows = res if isinstance(res, list) else []
            payload = _to_rows_payload(rows)
            total = payload.get("row_count", 0)
            return {"answer": f"Encontré {total} estudios para el paciente ID {patient_id}.", "data": payload, "steps": 1}
        return None

    async def _dashboard(self) -> Optional[Dict[str, Any]]:
        if "dashboard_stats" not in self.tools.allowed_tools:
            return None
        res = await self.tools.call("dashboard_stats")
        if isinstance(res, dict):
            lines = [f"- {k}: {v}" for k, v in res.items()]
            answer = "Resumen general del sistema:\n" + "\n".join(lines)
            return {"answer": answer, "data": {"rows": [], "row_count": 0, "raw": res}, "steps": 1}
        return None

    async def _citas_fastlane(self, question: str, want_count: bool) -> Optional[Dict[str, Any]]:
        if "citas_filter" not in self.tools.allowed_tools:
            return None
        dr = _extract_date_exact_or_range(question)
        filters = []
        if dr:
            filters = [
                {"field": "hora_inicio", "op": "gte", "value": dr[0]},
                {"field": "hora_inicio", "op": "lte", "value": dr[1]},
            ]
        args = {"filters": filters, "page": 1, "pageSize": 20}
        res = await self.tools.call("citas_filter", args)
        total = _extract_total_from_filter_tool(res) or 0
        if want_count:
            return {"answer": f"Total de citas: {total}.", "data": {"rows": [], "row_count": total, "raw": res}, "steps": 1}
        items = res.get("items", []) if isinstance(res, dict) else []
        payload = _to_rows_payload(items)
        answer = f"Encontré {total} citas." if total else "No se encontraron citas."
        return {"answer": answer, "data": payload, "steps": 1}

    async def query(self, question: str) -> Dict[str, Any]:
        q = _strip_accents_lc(question or "")
        wants_count = _is_count_request(q)
        is_list = _is_list_request(q)

        # Dashboard / estadísticas generales
        if _is_dashboard_intent(q) and not _is_pagos_intent(q):
            out = await self._dashboard()
            if out:
                return out

        # Pacientes
        if _is_patients_intent(q):
            out = await self._patients_via_patient_search(question, want_count=wants_count)
            if out:
                return out

        # Citas
        if _is_citas_intent(q):
            out = await self._citas_fastlane(question, want_count=wants_count)
            if out:
                return out

        # Pagos
        if _is_pagos_intent(q):
            out = await self._pagos(question, want_count=wants_count)
            if out:
                return out

        # Visitas
        if _is_visitas_intent(q):
            out = await self._visitas(question, want_count=wants_count)
            if out:
                return out

        # Estudios
        if _is_estudios_intent(q):
            out = await self._estudios(question, want_count=wants_count)
            if out:
                return out

        # Fallback: LLM — se construye lazy para leer .env correctamente
        try:
            llm_client, model_name = _build_llm_client()
            system_prompt = (
                "Eres un asistente médico del sistema SGP (Sistema de Gestión de Pacientes). "
                "Ayudas al personal de la clínica a consultar información sobre pacientes, citas y visitas. "
                "IMPORTANTE: Solo responde con datos reales del sistema. NO inventes datos, nombres, ni tablas. "
                "Si no puedes obtener datos reales, explica qué tipo de preguntas puedes responder. "
                "Puedes consultar: pacientes, citas, visitas, pagos, estudios, antecedentes y estadísticas del dashboard."
            )
            resp = llm_client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question},
                ],
                timeout=LLM_TIMEOUT,
            )
            answer = resp.choices[0].message.content or "Sin respuesta."
            return {"answer": answer, "data": {"rows": [], "row_count": 0}, "steps": 1}
        except Exception as e:
            return {"answer": f"No pude procesar la pregunta: {e}", "data": {"rows": [], "row_count": 0}, "steps": 0}

# =========================================================
# Bootstrap MCP Node
# =========================================================
async def ask_with_embedded_mcp(question: str) -> Dict[str, Any]:
    node_entry = os.getenv("NODE_MCP_ENTRY", "").strip()
    api_base_url = os.getenv("API_BASE_URL", "").strip()
    node_cwd = os.getenv("NODE_MCP_CWD", "").strip() or (os.path.dirname(node_entry) if node_entry else "")

    if not node_entry or not os.path.isfile(node_entry):
        return {"answer": "Falta NODE_MCP_ENTRY (usa dist/main.js).", "data": {"rows": [], "row_count": 0}, "steps": 0}
    if not api_base_url:
        return {"answer": "Falta API_BASE_URL.", "data": {"rows": [], "row_count": 0}, "steps": 0}
    if not node_cwd or not os.path.isdir(node_cwd):
        node_cwd = os.path.dirname(node_entry)

    env = {
        **os.environ,
        "API_BASE_URL": api_base_url,
        "NODE_NO_WARNINGS": "1",
        "HTTP_TIMEOUT_MS": os.getenv("HTTP_TIMEOUT_MS", "25000"),
    }

    # Usar tsx si el entry es .ts, node si es .js
    if node_entry.endswith(".ts"):
        tsx_bin = os.path.join(os.path.dirname(node_entry), "node_modules", ".bin", "tsx")
        if not os.path.isfile(tsx_bin):
            tsx_bin = "tsx"
        cmd = [tsx_bin, node_entry]
    else:
        cmd = ["node", node_entry]
    server_params = StdioServerParameters(
        command=cmd[0],
        args=cmd[1:],
        env=env,
        cwd=node_cwd,
    )

    _log_mcp("========================================")
    _log_mcp("Starting MCP Node via stdio...")
    _log_mcp(f"CWD: {node_cwd}")
    _log_mcp(f"CMD: {server_params.command} {' '.join(server_params.args or [])}")
    _log_mcp("========================================")

    try:
        with anyio.fail_after(OVERALL_TIMEOUT):
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    _log_mcp("ClientSession created. Initializing...")
                    with anyio.fail_after(MCP_INIT_TIMEOUT):
                        await session.initialize()
                    _log_mcp("✅ MCP initialize OK.")

                    tools = NodeMCPToolsProxy(session)
                    await tools.refresh_allowed_tools()

                    agent = MedicalAgentMCP(tools)
                    return await agent.query(question)

    except TimeoutError:
        _log_mcp(f"❌ OVERALL timeout ({OVERALL_TIMEOUT}s).")
        _diagnose_node_process_sync(cmd, env, cwd=node_cwd, seconds=5)
        return {"answer": f"Timeout total ({OVERALL_TIMEOUT}s).", "data": {"rows": [], "row_count": 0}, "steps": 0}
    except Exception as e:
        _log_mcp(f"❌ MCP failed: {repr(e)}")
        _diagnose_node_process_sync(cmd, env, cwd=node_cwd, seconds=5)
        return {"answer": f"Error MCP: {e}", "data": {"rows": [], "row_count": 0}, "steps": 0}

# Runner
class Runner:
    def run(self, question: str) -> Dict[str, Any]:
        return anyio.run(ask_with_embedded_mcp, question)