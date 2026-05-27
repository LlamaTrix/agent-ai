# Guia Breve: Agregar Tools al Proyecto (Sin Depender de IA)

Este proyecto ya tiene un MCP server (`mcp_server/`) con tools versionados y un agente Python que puede orquestarlos. La idea de "agregar tools de manera organica" es: crear capacidades nuevas como funciones tipadas y testeables, que se puedan invocar de forma directa (por nombre + argumentos), y dejar al LLM solo como una capa opcional de UX (lenguaje natural).

## Principios

1. Tool-first: cada feature nueva debe existir como un tool independiente con contrato claro (args/retorno).
2. Deterministico: el tool hace el trabajo sin depender de prompts ni "razonamiento".
3. Componible: preferir tools pequenos (listar, filtrar, resumen, export) que se puedan encadenar.
4. Seguro: validar argumentos (Zod), validar timeouts y no ejecutar acciones destructivas sin un "confirm".

## Donde vive cada cosa

- Tools MCP (Node/TS): `mcp_server/src/tools/`
- Registro central de tools: `mcp_server/src/tools/index.ts` (ver `registerAllTools`)
- Filtros/presets reutilizables: `mcp_server/src/filters/` y `mcp_server/src/presets/`
- Agente Python: `Refactor/python_agent/SQL_Server_AI_Agent_AUV.py`

## Flujo recomendado para crear un tool nuevo

### 1) Disenar el contrato del tool (sin IA)

Defini:
- Nombre: `snake_case` (ej: `patients_insurance_report`)
- Proposito (1 linea): que hace y a que endpoint pega
- Entrada (args): campos, tipos, opcionales, limites
- Salida: lista (`rows/items`) o dict (stats/report)
- Errores: que condiciones disparan error (y como se devuelve)

Regla practica: si el tool devuelve una lista grande, soporta `limit`, `sort`, `page/pageSize` o al menos `limit`.

### 2) Implementar en el MCP server (Node/TS)

1. Crea un archivo nuevo en `mcp_server/src/tools/`, por ejemplo:
   - `mcp_server/src/tools/insurance.ts`
2. Registra el tool con Zod y `server.tool(...)` (patron existente):
   - Mira `mcp_server/src/tools/patient.ts` como referencia.
3. Si tu tool es "reporte" (agregaciones, conteos, agrupaciones), implementa la logica en TS:
   - Evita delegar al LLM.
4. Reusa utilidades:
   - HTTP: `mcp_server/src/http.ts` (`httpGetJson`, `addQueryParams`)
   - Payload estandar: `mcp_server/src/payload.ts` (`okPayload`, `errPayload`)
   - Filtros: `applyFilterPipeline(...)` si aplica.

### 3) Registrar el tool en el indice

Edita `mcp_server/src/tools/index.ts` y agrega tu `registerXTools(server)` dentro de `registerAllTools`.

### 4) Probar el tool de forma directa (sin agente, sin IA)

Objetivo: que el tool funcione aunque el planner LLM falle.

Opciones:
- Llamada directa via el cliente MCP que ya uses en tu runner (ideal).
- O, al menos, un smoke-test interno (ejecutar el server y verificar que `list_tools` lo devuelve y que responde).

Si no hay suite de tests, aun asi conviene dejar un ejemplo de llamada en un `.md` o un script de prueba.

## Exponer el tool al agente Python (opcional)

Si queres que el agente LLM lo use automaticamente:

1. Agrega el nombre del tool a `_PLANNER_TOOLS` en:
   - `Refactor/python_agent/SQL_Server_AI_Agent_AUV.py`
2. Si el tool devuelve listas con forma particular y queres una tabla mas "humana", agrega un normalizador:
   - Ejemplo existente: `_flatten_patient_row(...)`
3. Si el tool devuelve un dict (stats/reporte), el agente ya lo pasa como `extra_context` cuando no hay `rows`.
4. Para mensajes automaticos del tipo "Encontré N ...", agrega el singular/plural a `_TOOL_NOUN`.

Si NO queres depender del LLM:

- Mantene el tool igual, pero llamalo desde el runner o tu UI/CLI por nombre (tool) + JSON (args).
- Recomendacion: agrega un modo "comando explicito" (ej: `/tool patient_filter {"preset":{"tiene_seguro":false},"limit":1000}`) y saltea la planificacion LLM cuando el input empieza con `/tool`.
  - Esto te permite agregar tools nuevos sin re-entrenar prompts ni "enseñar" nada al modelo.

## Tipos de tools que escalan bien (sin IA)

- Reportes: conteos, agrupaciones, "top N", estadisticas por periodo.
- Validadores: detectar datos faltantes o inconsistentes (seguro, estado civil, telefono, CI duplicado).
- Exportadores: export a CSV/XLSX desde el server (o devolver datos ya listos para export).
- "Shortcuts" deterministas: tools que encapsulan presets comunes (ej: `patients_without_insurance`) para no depender de que el planner arme el filtro correcto.
- Enriquecimiento: normalizar valores (estado civil, sexo, metodos de pago) a un set canonico.

## Checklist rapido (para cada tool)

- Tiene descripcion clara (para humanos, no para el LLM).
- Valida args con Zod.
- No depende de IA para producir el resultado.
- Soporta limites (`limit`) y evita traer datasets gigantes.
- Devuelve `okPayload/errPayload`.
- Queda registrado en `registerAllTools`.
- (Opcional) Queda agregado a `_PLANNER_TOOLS` si el agente debe invocarlo por lenguaje natural.

