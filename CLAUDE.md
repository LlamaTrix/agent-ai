# CLAUDE.md

Guía para trabajar en este repositorio. Léela antes de tocar código.

---

## 1. Qué es

Agente conversacional clínico para el sistema médico **SGP / drclic** (clínica/consultorio
odontológico-médico). El usuario hace una pregunta en español ("¿cuántos pacientes sin seguro hay?",
"¿de quién es la cita 52?", "odontogramas de Juan en abril") y el sistema:

1. Un **LLM planificador** decide qué herramienta (tool) usar y con qué argumentos.
2. Esa tool pega a la **API Laravel** del backend (`/api/v1/...`) y filtra los datos.
3. Un **LLM analizador** redacta la respuesta en lenguaje natural.
4. Devuelve además las filas crudas y un Excel descargable (base64).

**No hay base de datos SQL propia.** No se usa SQL Server ni conexión directa a BD: todo se consume vía
HTTP contra el Laravel existente, mediado por un servidor MCP. (El archivo principal se llamaba
`SQL_Server_AI_Agent_AUV.py` —nombre heredado y engañoso— y fue renombrado a `clinical_agent.py`.)

---

## 2. ⚠️ Estructura real del repo (importante)

El proyecto que se ejecuta vive **dentro de `Refactor/`**, no en la raíz:

```
agent-ai/
├── README.md, REFACTOR.md, GUIA_AGREGAR_TOOLS.md   ← docs (algunas DESACTUALIZADAS)
├── ecosystem.config.cjs, install.sh                ← ⚠️ apuntan a ./python_agent y ./mcp_server
│                                                      que NO existen en la raíz → no funcionan desde aquí
└── Refactor/                                       ← 👈 EL PROYECTO REAL
    ├── ecosystem.config.cjs   ← config pm2 válida (cwd ./python_agent)
    ├── install.sh             ← bootstrap válido
    ├── README.md / REFACTOR.md
    ├── python_agent/          ← Agente Python (FastAPI + Streamlit + orquestación LLM)
    │   ├── clinical_agent.py   ← núcleo (2000+ líneas): planner, tools, answerer
    │   ├── server.py          ← FastAPI, endpoint POST /askai (:8001)
    │   ├── app.py             ← UI Streamlit (:8501)
    │   ├── main.py            ← arranque dev local (legacy, no se usa con pm2)
    │   ├── tests/             ← tests unittest (test_agent.py) — sin LLM ni red
    │   ├── requirements.txt
    │   ├── .env.example
    │   └── exports/           ← Excel generado en runtime (gitignored)
    └── mcp_server/            ← Servidor MCP en TypeScript
        ├── main.ts            ← bootstrap stdio (25 líneas)
        ├── tsconfig.json      ← module: NodeNext
        ├── package.json       ← scripts: build, start, test
        ├── test/              ← tests node:test (pipeline.test.mjs)
        ├── .env.example
        └── src/
            ├── config.ts      ← env: API_BASE_URL, API_TOKEN, HTTP_TIMEOUT_MS
            ├── http.ts        ← httpGetJson, addQueryParams, fillPathTemplate, auth
            ├── payload.ts     ← okPayload / errPayload (envoltura MCP)
            ├── filters/       ← pipeline.ts (motor de filtros) + schema.ts (Zod)
            ├── presets/       ← person, patient, citas, visitas, antecedents
            └── tools/         ← una tool (o familia) por archivo + index.ts (registro central)
```

**Antes de cualquier trabajo: opera dentro de `Refactor/`.** Los archivos de la raíz son copias
quedadas y deberían consolidarse (ver §11).

---

## 3. Arquitectura y flujo de una petición

Son **dos procesos**, no uno:

- **Agente Python** (FastAPI + Streamlit) → orquesta los LLMs.
- **Servidor MCP** (Node/TS) → expone las tools que pegan a Laravel.

El agente **lanza el MCP como subprocess vía stdio** en cada petición (no es un servicio HTTP). pm2
solo administra los procesos Python; el MCP solo necesita estar compilado en `mcp_server/dist/`.

```
Usuario
  │  POST /askai {query}            (o UI Streamlit)
  ▼
server.py ─► ask_with_embedded_mcp()                [clinical_agent.py]
                │  spawnea  `node dist/main.js`  vía stdio  (StdioServerParameters)
                │  session.initialize() + list_tools()
                ▼
            MedicalAgentMCP.query(question):
              1. _plan()         → LLM THINKER (JSON mode) → {tool, args}
              2. overrides hardcodeados de routing (cita_by_id / odontogramas / cumpleaños / payments_filter)
              3. _normalize_tool_args()  → corrige forma de filters, alias de ops, campos derivados
              4. _resolve_patient_id()   → si el arg es un nombre, lo resuelve a ID (llamadas MCP extra)
              5. tools.call(tool, args)  → ejecuta en el MCP (1 reintento vía LLM si falla)
              6. _unwrap_rows() + _flatten_patient_row() + normalización de seguro/teléfono/estado civil
              7. _analyze()      → LLM ANSWERER → respuesta en español
              8. overrides de respuesta (vacío / odontograma / cita_by_id)
              9. _rows_to_excel_b64()
                ▼
            {answer, data:{rows,row_count}, excel_bytes, excel_name}

  En el MCP, cada tool:  httpGetJson(API_BASE_URL + /v1/...)  →  applyFilterPipeline(...)  →  okPayload
```

**Dos modelos LLM** (ver `.env`):
- **THINKER** (planificador): solo devuelve JSON con `{tool, args}`. Puede ser un modelo local pequeño
  (Ollama). Si no se configura, reusa el answerer.
- **ANSWERER** (analizador): genera la respuesta natural. Por defecto Groq `llama-3.3-70b-versatile`
  (compatible OpenAI).

### Detalles del flujo (para dominarlo)

- **Dos puntos de entrada al mismo motor:**
  - `app.py` (Streamlit) → `Runner().run()` → `anyio.run(ask_with_embedded_mcp, q)` (envoltura **síncrona**).
  - `server.py` (FastAPI) → `await ask_with_embedded_mcp(q)` (**async** directo).
  Ambos spawnean su propio subprocess MCP por llamada.
- **Envoltura de respuesta del MCP** (lo que devuelve cada tool): `{ok, tool, url, data}`, donde `data`
  del pipeline es `{total, page, pageSize, returned, items}`. El agente saca las filas con `_unwrap_rows`
  (busca `items`/`rows`/`data`/`results`).
- **`preset` vs `filters` vs `search`** en una tool de filtro: el `preset` (campos amigables tipo
  `tiene_seguro`) se traduce a `filters` vía `build<Dominio>PresetFilters`, y se **concatena** con los
  `filters` manuales (AND). `search` es texto libre sobre una lista de campos.
- **Presupuesto de tokens al answerer** (clave para los 429/TPM): antes de mandar las filas al LLM se
  pasa por `_compact_rows_for_llm` (recorta strings largos y limita profundidad), se toma una muestra de
  `MAX_ROWS_TO_LLM` filas y, si el JSON supera `MAX_LLM_INPUT_CHARS`, se va **reduciendo la muestra a la
  mitad** hasta entrar. El answerer recibe un encabezado `Total:N` con el conteo real aunque solo vea una
  muestra.
- **Reintento ante fallo de tool:** si `tools.call` lanza, el agente le pasa el error al thinker pidiendo
  que **corrija solo los args** y reintenta **una vez**.
- **Overrides de respuesta:** tras el answerer hay correcciones determinísticas: si el LLM dijo "no hay"
  pero el MCP trajo filas → responde `Encontré N <noun>`; y hay textos a medida para `odontogramas`
  vacíos y para `cita_by_id`.
- **Tabla en la UI:** `app.py` solo muestra la tabla si la pregunta contiene palabras como "tabla",
  "lista", "dame", "todos", etc. (heurística `_TABLE_WORDS`).

---

## 4. El servidor MCP (TypeScript)

### Patrón de filtrado: **client-side**
Cada tool hace **un GET a Laravel que trae la lista completa** y luego filtra/ordena/pagina **en JS**
con `applyFilterPipeline` ([Refactor/mcp_server/src/filters/pipeline.ts](Refactor/mcp_server/src/filters/pipeline.ts)).
No hay filtrado en el servidor Laravel → para tablas grandes esto trae todo cada vez (ver §12).

### Operadores de filtro soportados
`eq, neq, gt, gte, lt, lte, contains, startsWith, endsWith, in, exists, not_exists`
(definidos en [filters/schema.ts](Refactor/mcp_server/src/filters/schema.ts)).

### Campos derivados (calculados en el pipeline, prefijo `__`)
- `__has_phone` — tiene telf1/telf2/tel_referencia
- `__has_seguro` — tiene num_seguro o empresa_seg
- `__estado_civil` — el valor de estado civil (o null)
- `__has_birthdate` — fecha de nacimiento válida y "significativa" (ignora `0000-00-00`, futuros, < 1900)

Estos campos se **eliminan** de la salida (`stripInternalFields`) pero permiten filtros tipo "sin seguro".

### Catálogo de tools registradas ([tools/index.ts](Refactor/mcp_server/src/tools/index.ts))

| Tool | Archivo | Endpoint Laravel / nota |
|---|---|---|
| `person_list` / `person_get` | generic-get.ts | `/v1/person`, `/v1/person/{id}` |
| `patient_list` / `patient_get` | generic-get.ts | `/v1/patient`, `/v1/patient/{id}` |
| `patient_filter` | patient.ts | `/v1/patient` + preset (tiene_seguro, tiene_telefono, etc.) + filtros |
| `person_filter` | person.ts | `/v1/person` + preset |
| `citas_list` / `citas_by_patient` | generic-get.ts | `/v1/citas`, `/v1/citas/{patient_id}` |
| `citas_filter` | citas.ts | `/v1/citas` (o `/{patient_id}`) + preset |
| `cita_by_id` | cita-by-id.ts | busca una cita en `/v1/citas` y resuelve su paciente |
| `visitas_by_patient` / `visitas_by_cita` | generic-get.ts | `/v1/visitas/patient/{id}`, `/v1/visitas/{cita_id}` |
| `visitas_filter` | visitas.ts | by_patient / by_cita + preset |
| `odontogramas` | odontogramas.ts | `/v1/odontogramas` (o `/cita/{id}`, `/paciente/{id}`) + fallback inteligente |
| `medicamentos` | medicamentos.ts | `/v1/recetasMedicamentos` (catálogo de nombres únicos) |
| `payments_list` / `payments_by_patient` / `payments_statistics` | generic-get.ts | `/v1/payments`, `/v1/payments/{patientId}`, `/v1/payments/statistics` |
| `payments_filter` | payments.ts | `/v1/payments` + filtros (preferir sobre payments_list cuando hay filtros) |
| `estudios_by_patient` / `estudios_by_cita` | generic-get.ts | `/v1/estudios/...` |
| `recetas_by_visita` / `notas_by_cita` / `archivos_by_patient` | generic-get.ts | varios |
| `antecedents_unique_surgical` / `antecedents_get` | generic-get.ts + antecedents.ts | `/v1/antecedents/...` |
| `filter_json` | filter-json.ts | filtra un JSON arbitrario (utilidad genérica) |
| `clinic_bundle` | bundle.ts | **DESACTIVADO** (comentado en index.ts) |

El planificador no ve las ~26 tools; solo el subconjunto curado en `_PLANNER_TOOLS`
([clinical_agent.py](Refactor/python_agent/clinical_agent.py)).

---

## 5. Comandos y cómo correr en local

Todo vive en `Refactor/` (no en la raíz).

### ⚠️ Lo más importante de entender primero
El **agente Python arranca el MCP por sí mismo** (hace `node dist/main.js` por dentro, en cada
consulta). Por eso, para usar la UID/Streamlit **NO hace falta** correr `npm start` aparte. El MCP solo
necesita estar **compilado** (`dist/main.js` debe existir → `npm run build`). `npm start` es únicamente
para depurar el MCP aislado.

Entonces, para correr en local solo necesitás 3 cosas:
1. El **backend Laravel** corriendo (en este equipo: `API_BASE_URL=http://localhost:8000/api`).
2. El MCP **compilado** (`dist/main.js` presente).
3. **Streamlit** (o FastAPI) corriendo dentro del venv.

### Paso a paso (Windows / PowerShell)

```powershell
# (Solo la primera vez, o si cambian dependencias) Compilar el MCP
cd C:\Users\Usuario\Desktop\agent-ai\Refactor\mcp_server
npm install
npm run build            # tsc → genera dist/main.js  (REPETIR tras tocar cualquier .ts)

# Correr el agente
cd C:\Users\Usuario\Desktop\agent-ai\Refactor\python_agent
.\.venv\Scripts\Activate.ps1     # activa el venv → el prompt muestra (.venv)
streamlit run app.py --server.port 8501          # UI en http://localhost:8501
# (alternativa: la API) uvicorn server:app --port 8001   → POST /askai, GET /health
deactivate                       # al terminar
```

Si PowerShell bloquea el script de activación ("ejecución de scripts deshabilitada"), corré una vez por
terminal: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`.

### Sobre el venv (entorno virtual de Python)
Es una carpeta aislada (`.venv/`) con su propio Python y sus librerías, para no mezclar dependencias con
el Python global. Ciclo: **activar → trabajar → desactivar**. Ya está creado en este repo. Si hubiera que
recrearlo desde cero:
```powershell
cd C:\Users\Usuario\Desktop\agent-ai\Refactor\python_agent
python -m venv .venv                 # crea la carpeta .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt      # instala FastAPI, Streamlit, pandas, openai, mcp, etc.
```
Mientras `(.venv)` aparezca en el prompt, todo `python`/`pip`/`streamlit` usa el entorno aislado.

### Otros comandos útiles
```powershell
npm start          # (en mcp_server) correr el MCP standalone vía stdio — solo debug
npx tsc --noEmit   # (en mcp_server) type-check sin compilar
```

### Producción (Linux + pm2)
```bash
cd Refactor
pm2 start ecosystem.config.cjs       # agent-api (:8001) + agent-ui (:8501)
pm2 logs agent-api
```

> **Recordá:** tras cualquier cambio en `mcp_server/src/**` hay que recompilar (`npm run build`),
> porque el agente Python ejecuta `dist/main.js`, no los `.ts`.

---

## 6. Variables de entorno

`python_agent/.env` (ver `.env.example`):
- `NODE_MCP_ENTRY` — ruta absoluta a `mcp_server/dist/main.js` (la setea `install.sh`)
- `NODE_MCP_CWD` — directorio del mcp_server
- `API_BASE_URL` — URL del Laravel (ej. `https://.../api`)
- `LLM_PROVIDER` — `openai_compat` (default) o `azure`
- `LLM_ANSWERER_*` — API key / base URL / modelo del answerer (Groq por defecto)
- `LLM_THINKER_*` — opcional; si falta, el thinker reusa el answerer
- `MCP_INIT_TIMEOUT`, `MCP_TOOL_TIMEOUT`, `LLM_TIMEOUT`, `OVERALL_TIMEOUT`, `HTTP_TIMEOUT_MS`
- `MAX_ROWS_TO_LLM`, `MAX_CONCURRENT_REQUESTS`, `ALLOW_ORIGINS` (CORS)
- `MAX_RESULT_LIMIT` — tope de filas que se piden al MCP cuando el plan no fija paginación (default
  5000). Evita que el `pageSize=50` del pipeline trunque conteos/listas/Excel (ver §11 "ya resuelto").
- `DEBUG_MCP`, `MCP_LOG_FILE` — logging

`mcp_server/.env` (solo para correr el MCP standalone; en producción el agente inyecta estas vars al
spawnear el subprocess): `API_BASE_URL`, `API_TOKEN` (opcional, Bearer), `HTTP_TIMEOUT_MS`.

---

## 6.5. Groq y la capa LLM (explicado)

**Groq no es un modelo: es un proveedor de inferencia.** Fabrica un chip (la **LPU**) que ejecuta LLMs
mucho más rápido que una GPU, y *hostea* modelos open-source (Llama, etc.) detrás de una API.

- El modelo usado es **`llama-3.3-70b-versatile`** = Llama 3.3 70B de Meta, corriendo en hardware Groq.
  Groq = la nube veloz; Llama = el modelo.
- El código **no usa un SDK de Groq**: usa el **SDK de OpenAI** apuntado a
  `https://api.groq.com/openai/v1`, porque Groq ofrece una API **compatible con OpenAI**. De ahí
  `LLM_PROVIDER=openai_compat`. Para cambiar de proveedor (OpenAI real, Ollama local, etc.) basta con
  cambiar `LLM_*_BASE_URL` / `LLM_*_MODEL` / `LLM_*_API_KEY` — el código no cambia.

### Dos roles de LLM (¡pueden ser modelos distintos!)
- **THINKER** (planificador) — `_plan()`: recibe la pregunta + la lista de tools y devuelve **solo JSON**
  `{tool, args}`. Es la "decisión".
- **ANSWERER** (analizador) — `_analyze()`: recibe las filas y redacta la respuesta en español. Es la
  "redacción".

`_build_llm_clients()` arma ambos clientes. **Si `LLM_THINKER_BASE_URL`/`LLM_THINKER_MODEL` NO están en
el `.env`, el thinker reutiliza el cliente del answerer** → en la config actual de este equipo, **Groq
hace los dos roles**.

### Implicancia de costo/límites (importante)
Con thinker = answerer = Groq, **cada consulta hace 2 llamadas a Groq** (plan + análisis), +1 si hay
reintento, + las llamadas de resolución nombre→ID. El tier gratuito de Groq tiene límites por minuto
(RPM/TPM); al superarlos devuelve **HTTP 429** (los picos que se ven en el dashboard de Groq). Para
reducirlos: ver el roadmap (§13.5) — thinker local con Ollama y/o cache de planes.

---

## 7. Convenciones / gotchas

- **Imports relativos SIEMPRE con `.js`** en el MCP (TS usa `module: NodeNext`):
  `import { okPayload } from "../payload.js";` ✅ — sin extensión NO compila.
- **`McpServer` se importa como `import type`** en los módulos de tools.
- **Recompilar el MCP** tras tocar `src/**` (§5).
- El agente **descubre tools dinámicamente** con `session.list_tools()`; una tool nueva aparece sola en
  `allowed_tools`, **pero el planner no la usará** hasta agregarla a `_PLANNER_TOOLS` y describirla en
  `PLANNER_SYSTEM`.
- **Defensa contra prompt-injection**: `ANALYZER_SYSTEM` instruye a tratar el JSON solo como datos y los
  datos van envueltos en marcadores `=== DATOS_JSON_SEGUROS ===`. Mantené esto al tocar el answerer.
- **Contrato de respuesta estable**: `{answer, data:{rows, row_count}, excel_bytes, excel_name}`. El
  frontend depende de `rows`/`row_count`. No lo rompas.
- **Zona horaria**: fechas/edades se calculan con `America/La_Paz`.

---

## 8. Cómo agregar una tool nueva

### Caso A — GET simple a un endpoint Laravel
Agregá una línea al array `tools` en [generic-get.ts](Refactor/mcp_server/src/tools/generic-get.ts):
```ts
{ name: "lab_by_patient", description: "GET /v1/lab/{patientId}",
  path: "/v1/lab/{patientId}", inputShape: { patientId: z.string() } },
```
El loop genérico maneja registro, fetch, errores y payload.

### Caso B — tool con filtros client-side (estilo `citas_filter`)
1. Crear `src/presets/<dominio>.ts` (schema Zod + `build<Dominio>PresetFilters`).
2. Crear `src/tools/<dominio>.ts` con `register<Dominio>Tools(server)` (copiá `citas.ts`).
3. Registrar en `registerAllTools` en `src/tools/index.ts`.

### Caso C — lógica especial (multi-fetch, fallback)
Nuevo archivo en `src/tools/` con su `register...` + alta en `index.ts`. Modelo = `cita-by-id.ts` u
`odontogramas.ts`.

### Para que el agente la invoque por lenguaje natural
1. Agregá el nombre a `_PLANNER_TOOLS`.
2. Describí el dominio/campos en `PLANNER_SYSTEM`.
3. (Opcional) singular/plural en `_TOOL_NOUN` para los mensajes "Encontré N ...".
4. Si devuelve filas con forma rara, considerá un normalizador estilo `_flatten_patient_row`.

Filosofía del repo (ver `GUIA_AGREGAR_TOOLS.md`): **tool-first y determinístico** — la tool debe
funcionar aunque el LLM falle; el LLM es solo la capa de UX en lenguaje natural.

---

## 9. Dónde tocar cada cosa

| Quiero… | Archivo |
|---|---|
| Cambiar cómo el planner elige tool / describir el esquema de datos | `PLANNER_SYSTEM` y `_PLANNER_TOOLS` en `clinical_agent.py` |
| Cambiar el tono/reglas de la respuesta final | `ANALYZER_SYSTEM` |
| Arreglar routing de una intención (citas, odontogramas, cumpleaños) | overrides en `MedicalAgentMCP.query` (líneas ~1334–1391) |
| Coerción de args del planner (forma de filters, alias de ops) | `_normalize_tool_args` |
| Resolución nombre→ID de paciente | `_resolve_patient_id` |
| Aplanar/normalizar filas de paciente para el LLM/Excel | `_flatten_patient_row` |
| Lógica de un tool MCP (endpoint, fallback) | `Refactor/mcp_server/src/tools/<x>.ts` |
| Operadores o motor de filtros | `Refactor/mcp_server/src/filters/pipeline.ts` |
| Presets reutilizables (campos amigables → filtros) | `Refactor/mcp_server/src/presets/<x>.ts` |
| Endpoint HTTP / API expuesta | `Refactor/python_agent/server.py` |
| UI | `Refactor/python_agent/app.py` |

---

## 10. Estado real vs. lo que dicen los docs

El docstring del agente afirma *"Sin reglas hardcodeadas de intención ni extractores de keywords"*.
**En la práctica es híbrido**: el LLM planifica, pero hay bastante routing y extracción por regex
encima (`_extract_cita_id_query`, `_looks_like_odontograma_query`, ruteo de cumpleaños, `payments_list
→ payments_filter`, alias de campos). No es un bug, pero al modificar conviene saber que **el plan del
LLM puede ser sobre-escrito** por estas reglas antes de ejecutar la tool.

---

## 11. Qué mejorar — deuda técnica / limpieza

### ✅ Ya resuelto (en este pase)
- **Citas filtradas por atributos del paciente (sexo/edad).** En una cita el paciente viene anidado en
  `patient.persona.*`, pero el LLM filtraba por `sexo`/`persona.sexo` (inexistentes en la cita) → 0.
  En `query()`, para tools de citas, se inyectan filtros sobre `patient.persona.sexo` /
  `patient.persona.fecha_nacimiento` (`_extract_sexo_positive` + `_extract_age_filters`), manteniendo el
  filtro de mes/fecha del LLM. No requiere cruzar tablas: la cita ya trae al paciente embebido.
  Además `_flatten_cita_row` sube `patient_sexo`/`patient_nombre`/`patient_edad` al nivel raíz: el LLM
  compacta a 2 niveles y si no, "ve" `patient.persona.sexo` como `"[obj]"` y respondía "el campo sexo
  está oculto" (aunque el filtro y el Excel estaban bien). El override de "Encontré N" también detecta
  esas frases de confusión.
- **Sexo: sinónimos y negaciones.** La BD usa `Masculino|Femenino|Otro`; el LLM fallaba con
  "varón/mujer/niño/niña" (inexistentes → 0) y con negaciones. Dos capas:
  `_canonical_sexo` (en `_normalize_tool_args`, `_SEXO_SYNONYMS`) normaliza el valor de cualquier filtro
  de sexo (incl. `op:"in"`); y `_extract_sexo_exclusions` resuelve **"que no sean A ni/o B"** de forma
  determinística (inyecta filtros `neq` en `query()`), sin depender de que el LLM arme la negación.
- **Filtros de edad ("mayores/menores a N años") que no se aplicaban.** Antes la conversión edad→fecha
  la hacía el LLM (mal) → "mayores a 10" y "menores a 10" devolvían lo mismo. Ahora `_extract_age_filters`
  + `_birthdate_cutoff` traducen la edad a un corte exacto sobre `persona.fecha_nacimiento` en el código
  (el LLM ya no calcula fechas). Las fechas explícitas (rango entre X e Y) ya funcionaban y no se tocaron.
- **Conteos que no cuadraban (pageSize=50 + LLM contando la muestra).** El pipeline pagina con
  `pageSize=50`, y el agente usaba `len(rows)` como conteo descartando el `total` real del MCP →
  "pacientes masculinos" devolvía 50 aunque hubiera cientos. Fix en `clinical_agent.py`:
  - `_ensure_result_limit` inyecta `limit=MAX_RESULT_LIMIT` cuando el plan no fija paginación → trae el
    conjunto completo (listas/Excel completos).
  - Se usa el `total` autoritativo del MCP (`raw["total"]`) para el encabezado del answerer, los overrides
    y el `row_count`.
  - **Respuesta de conteo determinística:** si la pregunta es de tipo "cuántos…" (`_is_count_question`),
    se responde `Hay N <noun>.` con el total real, **sin depender de que el LLM cuente bien** (antes el
    LLM contaba la muestra de filas que veía → decía "50" con 1049 filas reales).
- **Renombrado** `SQL_Server_AI_Agent_AUV.py` → `clinical_agent.py` (se actualizaron `server.py` y
  `app.py`; el nombre viejo aludía a un SQL Server inexistente).
- **`requirements.txt` limpio**: se quitaron `sqlalchemy` y `mysql-connector-python` (no se importaban).
  `openpyxl` se mantiene porque **sí** se usa en `_rows_to_excel_b64`.
- **Mojibake de encoding** corregido en [payments.ts](Refactor/mcp_server/src/tools/payments.ts).
- **`clinic_bundle` muerto** quitado de `_PLANNER_TOOLS` y del fallback de `allowed_tools`.
- **Suite de tests** creada (antes no había ninguna): ver §12.5.

### Pendiente
1. **Consolidar raíz vs `Refactor/`.** Hoy hay docs y configs duplicados en la raíz que apuntan a rutas
   inexistentes (`./python_agent`, `./mcp_server`). Decisión recomendada: mover `Refactor/` a la raíz
   (o borrar los duplicados de la raíz) para que `ecosystem.config.cjs` e `install.sh` de la raíz
   funcionen. **OJO:** mover `Refactor/` rompe el `.venv` (tiene rutas absolutas) y el `NODE_MCP_ENTRY`
   del `.env` → hay que recrear el venv y reapuntar el `.env`. Por eso no se hizo automáticamente.
2. **Archivo monolítico de 2000+ líneas** (`clinical_agent.py`). El MCP ya se dividió por dominio; el
   agente Python no. Conviene separar: extractores, prompts, orquestación, normalizadores, bootstrap.
   Hacerlo **ahora que hay tests** (§12.5) es seguro.
3. **`main.py` es legacy** (arranque dev manual). pm2 no lo usa. Documentar o borrar.
4. **`bundle.ts` (`clinic_bundle`) sigue comentado** en `index.ts`. Si no se va a usar, borrá el archivo;
   si sí, reactivalo y volvé a listarlo en `_PLANNER_TOOLS`.

---

## 12. Qué mejorar — performance y escalabilidad

1. **Subprocess MCP por petición.** Cada `/askai` hace spawn de `node`, `initialize` y `list_tools`
   antes de responder. Con `MAX_CONCURRENT_REQUESTS=3` esto es costoso y añade latencia. Considerar un
   MCP **persistente** (servicio HTTP/long-lived) y reusar la sesión.
2. **Filtrado client-side trae la tabla completa.** `applyFilterPipeline` filtra en JS tras un GET sin
   filtros del lado servidor. Para `patient`/`citas`/`payments` grandes esto descarga todo en cada
   consulta. Si el Laravel soporta query params de filtro, empujar el filtro al servidor (usar `query`).
3. **Hasta 2–3 llamadas LLM por consulta** (thinker + answerer + posible retry) más las llamadas de
   `_resolve_patient_id`. Cachear resolución nombre→ID y plans frecuentes ayudaría.
4. **Excel se genera siempre que hay filas**, aunque el usuario no lo pida. Generarlo bajo demanda.

---

## 12.5. Tests (red de seguridad sin LLM ni red)

Antes no había ninguna suite. Se agregaron tests **deterministas** (no llaman al LLM ni a Laravel), que
son la base para poder refactorizar el monolito sin romper nada.

### MCP server (TypeScript) — `mcp_server/test/pipeline.test.mjs`
Cubre el motor de filtros [pipeline.ts](Refactor/mcp_server/src/filters/pipeline.ts): cada operador,
campos derivados (`__has_seguro`, `__has_phone`, `__has_birthdate` con `0000-00-00`/futuros), `search`,
`sort`, `limit`, paginación, `select` y `stripInternalFields`. Corre contra el JS compilado (`dist/`).
```powershell
cd Refactor\mcp_server
npm test        # hace `npm run build` y luego `node --test test/`
```

### Agente Python — `python_agent/tests/test_agent.py`
Cubre `_normalize_tool_args` (coerción de filtros, alias de ops, mapeo a campos `__`, detección de
prefijo) y los extractores puros (`_extract_cita_id_query`, `_looks_like_odontograma_query`,
`_extract_sexo`, `_extract_blood_type`, `_age_details_from_birthdate`, `_unwrap_rows`).
```powershell
cd Refactor\python_agent
.\.venv\Scripts\Activate.ps1
python -m unittest discover -s tests -v
```

> Al agregar lógica nueva a un extractor / al pipeline, **agregá su test acá**. Es barato y evita
> regresiones silenciosas en las reglas de routing.

---

## 13. Recomendaciones extra

- **Tests determinísticos sin LLM.** Lo más valioso primero: tests del `applyFilterPipeline` (cada
  operador, campos derivados, paginación) y de `_normalize_tool_args`. Son puro código, sin red.
  Smoke-test del MCP: arrancar `dist/main.js`, `list_tools`, verificar el set esperado.
- **Modo "comando explícito"** (sugerido en `GUIA_AGREGAR_TOOLS.md`): permitir `/tool patient_filter
  {...json...}` para saltear el LLM y llamar tools directo. Útil para QA, scripts y para no depender del
  planner.
- **Privacidad / datos clínicos.** Se envían datos de pacientes (PII médica) a un LLM externo (Groq).
  Para un contexto clínico real, evaluar: minimizar campos enviados (`select`), anonimizar, o usar un
  modelo on-prem para el answerer. El thinker ya puede ser local (Ollama).
- **Auth hacia Laravel.** El MCP soporta `API_TOKEN` (Bearer) pero `.env.example` lo deja comentado. Si
  el backend exige auth, asegurate de que `API_TOKEN` esté en el entorno (se hereda al subprocess vía
  `os.environ`).
- **Observabilidad.** Hay `_log` con `DEBUG_MCP`/`MCP_LOG_FILE`. Para producción conviene logging
  estructurado (qué tool, args, latencia, tokens) para depurar planes erróneos del LLM.
- **Manejo de error del planner.** Si el LLM no devuelve JSON válido, el plan cae a `{tool:null}` y se
  responde "no hay datos". Un fallback a reglas (las que ya existen) o un mensaje más claro mejoraría UX.

---

## 13.5. Complejidad y roadmap de mejoras (guía para evolucionar el agente)

### ¿Qué tan complejo es?
Complejidad **media y desigual**:

| Parte | Nivel | Por qué |
|---|---|---|
| MCP server (TS) | 🟢 Baja | Modular, una tool por archivo, patrón repetido. Fácil de extender. |
| Arquitectura general | 🟡 Media | Varias piezas (2 procesos, subprocess stdio, 2 roles LLM) pero cada una entendible. |
| Agente Python | 🔴 Alta de mantener | Monolito de 2000+ líneas con muchos extractores regex y reglas de routing acumuladas. No es difícil algorítmicamente, sí de navegar/modificar sin romper algo. |

El verdadero punto de fricción es el monolito Python. Dividirlo (deuda §11.4) lo vuelve cómodo de
dominar.

### ¿El rendimiento depende del LLM?
- **Latencia (velocidad): casi NO.** Groq ya es de los más rápidos del mercado; el cuello de botella es
  **arquitectónico**, no el modelo.
- **Límites 429: SÍ, en parte.** Dependen de cuánta carga le mandás a Groq → reducible bajando llamadas.
- **Precisión: SÍ.** Un planner (thinker) mejor elige la tool correcta más seguido → menos reintentos y
  menos respuestas equivocadas. Ahí el modelo importa.

### Roadmap priorizado (orden sugerido para las mejoras)

**Antes de tocar nada (cimientos):**
1. **Consolidar raíz vs `Refactor/`** (§11.1) — para no perder tiempo con configs que engañan.
2. **Tests del `applyFilterPipeline` y `_normalize_tool_args`** (§13) — red de seguridad sin LLM, para
   refactorizar tranquilo.

**Ganancias de rendimiento que NO dependen del LLM (las más rentables):**
3. **MCP persistente** — dejar de hacer spawn/initialize/list_tools por request (§12.1). Mayor win de
   latencia.
4. **Filtrado server-side en Laravel** — dejar de bajar la tabla completa (§12.2). Mayor win con datos
   grandes.
5. **Excel bajo demanda + cache nombre→ID** (§12.3/§12.4).

**Para frenar los 429 y mejorar precisión (SÍ dependen del LLM):**
6. **Separar el thinker** a un modelo local (Ollama) o más barato → ~50% menos llamadas a Groq. Setear
   `LLM_THINKER_BASE_URL` / `LLM_THINKER_MODEL` en el `.env` (el código ya lo soporta).
7. **Cache de planes** para preguntas frecuentes (saltea el thinker).
8. **Reducir tokens al answerer** (`select` de campos, menos filas) → menos TPM, respuestas más rápidas.

**Calidad/mantenibilidad a mediano plazo:**
9. **Modularizar el agente Python** (§11.4).
10. **Modo "comando explícito"** `/tool nombre {json}` para QA sin LLM (§13).
11. **Logging estructurado** (tool, args, latencia, tokens) para depurar planes del LLM (§13).

> Regla mental: **¿querés que vaya más rápido?** arreglá la arquitectura (3–5). **¿que deje de chocar con
> 429?** bajá la carga sobre Groq (6–8). **¿que acierte más?** ahí sí mejorá el modelo planificador (6).

---

## 14. Referencias rápidas

- Núcleo del agente: [Refactor/python_agent/clinical_agent.py](Refactor/python_agent/clinical_agent.py)
- Registro de tools: [Refactor/mcp_server/src/tools/index.ts](Refactor/mcp_server/src/tools/index.ts)
- Motor de filtros: [Refactor/mcp_server/src/filters/pipeline.ts](Refactor/mcp_server/src/filters/pipeline.ts)
- Guía para agregar tools: [GUIA_AGREGAR_TOOLS.md](GUIA_AGREGAR_TOOLS.md)
- Historia del refactor del MCP: [REFACTOR.md](REFACTOR.md)
