# Refactor mcp_server — split por dominio

Fecha: 2026-04-30
Alcance: solo `mcp_server/`. **Sin cambios funcionales** — el comportamiento de cada tool, sus nombres, sus inputs y sus outputs son idénticos al de la versión previa. Es un movimiento mecánico de código para que dejar de tener un único `main.ts` de 864 líneas.

## Estructura nueva

```
mcp_server/
├── main.ts                          ← 24 líneas: bootstrap stdio
├── tsconfig.json                    ← include extendido a src/**
├── package.json                     ← sin cambios
└── src/
    ├── config.ts                    ← env: API_BASE_URL, API_TOKEN, HTTP_TIMEOUT_MS
    ├── http.ts                      ← httpGetJson, httpPostJson, addQueryParams,
    │                                  fillPathTemplate, buildAuthHeader
    ├── payload.ts                   ← okPayload, errPayload (envoltura MCP)
    ├── filters/
    │   ├── pipeline.ts              ← applyFilterPipeline + ops + FilterSpec +
    │   │                              getByPath, pickArray, toComparable, compareOp
    │   └── schema.ts                ← filterOps (zod enum), filterSchemaBase
    ├── presets/
    │   ├── person.ts                ← personPresetSchema + buildPersonPresetFilters
    │   ├── citas.ts                 ← citasPresetSchema + buildCitasPresetFilters
    │   ├── visitas.ts               ← visitasPresetSchema + buildVisitasPresetFilters
    │   └── antecedents.ts           ← antecedentsPresetSchema + builder
    └── tools/
        ├── index.ts                 ← registerAllTools(server): orquesta todo
        ├── generic-get.ts           ← person_list, person_get, patient_list,
        │                              patient_get, citas_list, citas_by_patient,
        │                              visitas_by_patient, visitas_by_cita,
        │                              antecedents_unique_surgical, antecedents_get
        ├── filter-json.ts           ← filter_json (genérico)
        ├── person.ts                ← person_filter
        ├── citas.ts                 ← citas_filter
        ├── visitas.ts               ← visitas_filter
        ├── antecedents.ts           ← antecedents_filter
        └── bundle.ts                ← clinic_bundle (orquestador)
```

## Antes vs después

| Antes | Después |
|---|---|
| `mcp_server/main.ts` (864 líneas, todo mezclado) | `main.ts` (24 líneas) + 16 archivos en `src/` |
| `tsconfig.include = ["main.ts"]` | `tsconfig.include = ["main.ts", "src/**/*.ts"]` |
| `version: "1.0.3"` en `McpServer` | `version: "1.1.0"` |
| `dist/main.js` | `dist/main.js` + `dist/src/**/*.js` (mismo entry) |

## Compatibilidad

- **Misma entry**: `NODE_MCP_ENTRY=.../mcp_server/dist/main.js` sigue funcionando sin cambios.
- **Mismas tools registradas**: `list_tools()` devuelve exactamente el mismo conjunto.
- **Mismos schemas Zod**: el agente Python no tiene que cambiar nada.
- **Mismos endpoints HTTP**: ninguna URL al App Service Laravel cambió.

## Validación realizada

```bash
cd mcp_server
npm install            # instala deps (no había node_modules)
npx tsc --noEmit       # type-check sin errores
npm run build          # genera dist/ correctamente
```

`dist/` resultante:

```
dist/main.js
dist/src/config.js
dist/src/http.js
dist/src/payload.js
dist/src/filters/{pipeline,schema}.js
dist/src/presets/{person,citas,visitas,antecedents}.js
dist/src/tools/{index,generic-get,filter-json,person,citas,visitas,antecedents,bundle}.js
```

## Cómo agregar una tool nueva ahora

### Caso A — GET simple a un endpoint Laravel
Agregar una entrada al array `tools` en [`src/tools/generic-get.ts`](mcp_server/src/tools/generic-get.ts):

```ts
{ name: "payments_list",
  description: "GET /v1/payments",
  path: "/v1/payments" },

{ name: "payments_by_patient",
  description: "GET /v1/payments/{patientId}",
  path: "/v1/payments/{patientId}",
  inputShape: { patientId: z.string() } },
```

Una línea por tool. El loop genérico se encarga del registro, fetch, error handling y `okPayload/errPayload`.

### Caso B — Tool con filtros client-side (estilo `citas_filter`)
1. Crear `src/presets/<dominio>.ts` con el schema Zod del preset y el `build<Dominio>PresetFilters`.
2. Crear `src/tools/<dominio>.ts` con una `register<Dominio>Tools(server)` siguiendo el patrón de `src/tools/citas.ts`.
3. Agregar la llamada a `registerAllTools` en `src/tools/index.ts`.

### Caso C — Tool con lógica especial (orquestador, multi-fetch, etc.)
Crear directo un nuevo archivo en `src/tools/` con su `register<X>Tool(server)` y agregarlo en `src/tools/index.ts`. Patrón = `src/tools/bundle.ts`.

## Notas importantes para mantener

- **Imports relativos siempre con `.js`**: el `tsconfig` usa `module: "NodeNext"` que exige extensión explícita en los imports incluso desde `.ts`. Ejemplo:
  ```ts
  import { okPayload } from "../payload.js";  // ✅
  import { okPayload } from "../payload";     // ❌ no compila
  ```
- **Type-only imports**: `McpServer` se importa como tipo (`import type { McpServer }`) en los módulos de tools, evitando re-evaluar el SDK por archivo.
- El agente Python descubre tools dinámicamente con `session.list_tools()` ([`SQL_Server_AI_Agent_AUV.py:438`](python_agent/SQL_Server_AI_Agent_AUV.py#L438)). Cualquier tool nueva aparece automáticamente en `allowed_tools` — pero **no se invoca** hasta que el router de intenciones la cablee.

## Lo que NO se tocó

- `python_agent/` — todo el agente Python sigue igual (router por intención hardcodeado, fallback a LLM, bugs conocidos).
- Los nombres y firmas de las tools.
- `package.json`, dependencias, scripts.
- `.env.example`, `ecosystem.config.cjs`.

## Próximos pasos sugeridos (no aplicados aún)

1. **Cablear tools que ya existen**: el agente Python espera `patient_search`, `payments_*`, `dashboard_stats`, `estudios_*`, `recetas_*` que **no existen** en el MCP. Confirmado contra `routes/api.php` del backend SGP que el Laravel sí tiene esos endpoints; falta crear las tools (caso A o B según corresponda) y cablearlas desde el agente.
2. **Bugs del router del agente Python**:
   - `_visitas` checkea `patient_search` en vez de `visitas_by_patient` ([`SQL_Server_AI_Agent_AUV.py:708`](python_agent/SQL_Server_AI_Agent_AUV.py#L708)).
   - Orden de intenciones: "paciente" gana sobre "cita" → "cuántas citas tuvo el paciente 5" devuelve TODAS las citas.
   - Cualquier número se asume `patient_id` en `_visitas`/`_estudios`.
   - `_extract_nombre` mete tokens irrelevantes como filtro `nombre LIKE ...`.
3. **Limpieza**: borrar `requirements.txt` no usados (`sqlalchemy`, `mysql-connector-python`, `openpyxl`), eliminar variables de entorno leídas y nunca usadas (`NATURALIZE_*`, `MAX_TOOL_STEPS`).
