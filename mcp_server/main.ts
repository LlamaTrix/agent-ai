import { z } from "zod";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

// =======================
// Config
// =======================
const API_BASE_URL = (process.env.API_BASE_URL || "").replace(/\/+$/, "");
const API_TOKEN = (process.env.API_TOKEN || process.env.API_AUTH || "").trim();
const HTTP_TIMEOUT_MS = Number(process.env.HTTP_TIMEOUT_MS || "30000");

function buildAuthHeader(token: string) {
  if (!token) return undefined;
  return token.toLowerCase().startsWith("bearer ") ? token : `Bearer ${token}`;
}

function fillPathTemplate(path: string, params: Record<string, unknown>) {
  return path.replace(/\{([^}]+)\}/g, (_, key) => {
    const v = (params as any)[key];
    if (v === undefined || v === null || String(v).length === 0) {
      throw new Error(`Missing required path param: ${key}`);
    }
    return encodeURIComponent(String(v));
  });
}

function addQueryParams(url: string, query?: Record<string, any>) {
  if (!query || typeof query !== "object") return url;
  const u = new URL(url);
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || String(v) === "") continue;
    if (Array.isArray(v)) for (const item of v) u.searchParams.append(k, String(item));
    else u.searchParams.set(k, String(v));
  }
  return u.toString();
}

// =======================
// HTTP helpers
// =======================
async function httpGetJson(url: string) {
  const headers: Record<string, string> = { Accept: "application/json" };
  const auth = buildAuthHeader(API_TOKEN);
  if (auth) headers["Authorization"] = auth;

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), HTTP_TIMEOUT_MS);

  try {
    const res = await fetch(url, { method: "GET", headers, signal: ctrl.signal });
    const text = await res.text();

    let body: any = text;
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      // keep string
    }

    if (!res.ok) {
      const msg = typeof body === "object" && body ? JSON.stringify(body) : String(body ?? "");
      throw new Error(`HTTP ${res.status} ${res.statusText}: ${msg}`);
    }
    return body;
  } catch (e: any) {
    if (e?.name === "AbortError") throw new Error(`Timeout HTTP (${HTTP_TIMEOUT_MS}ms) para: ${url}`);
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

async function httpPostJson(url: string, payload: any) {
  const headers: Record<string, string> = {
    Accept: "application/json",
    "Content-Type": "application/json",
  };
  const auth = buildAuthHeader(API_TOKEN);
  if (auth) headers["Authorization"] = auth;

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), HTTP_TIMEOUT_MS);

  try {
    const res = await fetch(url, {
      method: "POST",
      headers,
      body: payload === undefined ? undefined : JSON.stringify(payload),
      signal: ctrl.signal,
    });
    const text = await res.text();

    let body: any = text;
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      // keep string
    }

    if (!res.ok) {
      const msg = typeof body === "object" && body ? JSON.stringify(body) : String(body ?? "");
      throw new Error(`HTTP ${res.status} ${res.statusText}: ${msg}`);
    }

    return body;
  } catch (e: any) {
    if (e?.name === "AbortError") throw new Error(`Timeout HTTP (${HTTP_TIMEOUT_MS}ms) para: ${url}`);
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

function okPayload(tool: string, url: string, data: any) {
  return {
    content: [{ type: "text" as const, text: JSON.stringify({ ok: true, tool, url, data }, null, 2) }],
  };
}
function errPayload(tool: string, error: unknown) {
  return {
    content: [
      {
        type: "text" as const,
        text: JSON.stringify({ ok: false, tool, error: (error as any)?.message ?? String(error) }, null, 2),
      },
    ],
    isError: true,
  };
}

// =======================
// Dot-path utils + filter engine
// =======================
function getByPath(obj: any, path: string) {
  if (!path) return undefined;
  const parts = path.split(".").filter(Boolean);
  let cur = obj;
  for (const p of parts) {
    if (cur == null) return undefined;
    cur = cur[p];
  }
  return cur;
}

function pickArray(input: any, arrayPath?: string) {
  if (arrayPath && arrayPath.trim()) {
    const v = getByPath(input, arrayPath.trim());
    if (!Array.isArray(v)) throw new Error(`arrayPath '${arrayPath}' no apunta a un array.`);
    return v;
  }
  if (Array.isArray(input)) return input;
  for (const k of ["data", "items", "results", "rows"]) {
    if (Array.isArray((input as any)?.[k])) return (input as any)[k];
  }
  throw new Error("No pude encontrar un array. Pasa un array directo o usa arrayPath (ej: 'data').");
}

function toComparable(v: any) {
  if (v == null) return null;
  if (typeof v === "number") return v;
  if (typeof v === "boolean") return v ? 1 : 0;
  if (typeof v === "string") {
    const s = v.trim();
    const ms = Date.parse(s);
    if (!Number.isNaN(ms)) return ms;
    const num = Number(s);
    if (!Number.isNaN(num) && s !== "") return num;
    return s.toLowerCase();
  }
  return v;
}

function compareOp(a: any, op: string, b: any) {
  const A = toComparable(a);
  const B = toComparable(b);
  switch (op) {
    case "eq":
      return A === B;
    case "neq":
      return A !== B;
    case "gt":
      return A != null && B != null && (A as any) > (B as any);
    case "gte":
      return A != null && B != null && (A as any) >= (B as any);
    case "lt":
      return A != null && B != null && (A as any) < (B as any);
    case "lte":
      return A != null && B != null && (A as any) <= (B as any);
    case "contains":
      return a != null && String(a).toLowerCase().includes(String(b ?? "").toLowerCase());
    case "startsWith":
      return a != null && String(a).toLowerCase().startsWith(String(b ?? "").toLowerCase());
    case "endsWith":
      return a != null && String(a).toLowerCase().endsWith(String(b ?? "").toLowerCase());
    case "in":
      return Array.isArray(b) && b.some((x) => toComparable(x) === A);
    case "exists":
      return a !== undefined && a !== null && String(a) !== "";
    default:
      throw new Error(`Unsupported operator: ${op}`);
  }
}

type FilterSpec = { field: string; op: string; value?: any };

function applyFilterPipeline(params: {
  input: any;
  arrayPath?: string;
  filters?: FilterSpec[];
  search?: { text: string; fields: string[] };
  sort?: { field: string; direction?: "asc" | "desc" };
  page?: number;
  pageSize?: number;
  select?: string[];
  limit?: number;
}) {
  const { input, arrayPath, filters = [], search, sort, page = 1, pageSize = 50, select, limit } = params;

  const arr = pickArray(input, arrayPath);
  let out = arr.slice(); // ✅ nunca recortar antes de filtrar

  out = out.filter((item: any) => {
    for (const f of filters) {
      const val = getByPath(item, f.field);
      if (!compareOp(val, f.op, f.value)) return false;
    }
    return true;
  });

  if (search?.text && Array.isArray(search.fields) && search.fields.length) {
    const q = String(search.text).toLowerCase();
    out = out.filter((item: any) =>
      search.fields.some((field: string) => {
        const v = getByPath(item, field);
        return v != null && String(v).toLowerCase().includes(q);
      })
    );
  }

  if (sort?.field) {
    const dir = sort.direction === "desc" ? -1 : 1;
    out.sort((a: any, b: any) => {
      const A = toComparable(getByPath(a, sort.field));
      const B = toComparable(getByPath(b, sort.field));
      if (A == null && B == null) return 0;
      if (A == null) return 1;
      if (B == null) return -1;
      if ((A as any) < (B as any)) return -1 * dir;
      if ((A as any) > (B as any)) return 1 * dir;
      return 0;
    });
  }

  // ✅ limit DESPUÉS de filtrar/buscar/ordenar
  if (limit) out = out.slice(0, limit);

  const total = out.length;
  const start = (page - 1) * pageSize;
  const paged = out.slice(start, start + pageSize);

  const finalItems =
    Array.isArray(select) && select.length
      ? paged.map((item: any) => {
          const obj: any = {};
          for (const f of select) obj[f] = getByPath(item, f);
          return obj;
        })
      : paged;

  return { total, page, pageSize, returned: finalItems.length, items: finalItems };
}

// =======================
// Tool registry (endpoints GET)
// =======================
type ToolDef = { name: string; description: string; path: string; inputShape?: Record<string, z.ZodTypeAny> };

const tools: ToolDef[] = [
  { name: "person_list", description: "GET /v1/person", path: "/v1/person" },
  { name: "person_get", description: "GET /v1/person/{id}", path: "/v1/person/{id}", inputShape: { id: z.string() } },

  { name: "patient_list", description: "GET /v1/patient", path: "/v1/patient" },
  { name: "patient_get", description: "GET /v1/patient/{id}", path: "/v1/patient/{id}", inputShape: { id: z.string() } },

  { name: "citas_list", description: "GET /v1/citas", path: "/v1/citas" },
  {
    name: "citas_by_patient",
    description: "GET /v1/citas/{patient_id}",
    path: "/v1/citas/{patient_id}",
    inputShape: { patient_id: z.string() },
  },

  {
    name: "visitas_by_patient",
    description: "GET /v1/visitas/patient/{patientId}",
    path: "/v1/visitas/patient/{patientId}",
    inputShape: { patientId: z.string() },
  },
  { name: "visitas_by_cita", description: "GET /v1/visitas/{citaId}", path: "/v1/visitas/{citaId}", inputShape: { citaId: z.string() } },

  { name: "antecedents_unique_surgical", description: "GET /v1/antecedents/surgical", path: "/v1/antecedents/surgical" },
  { name: "antecedents_get", description: "GET /v1/antecedents/{id}", path: "/v1/antecedents/{id}", inputShape: { id: z.string() } },
];

// =======================
// MCP Server
// =======================
const server = new McpServer({ name: "clinic-api-get", version: "1.0.3" });

// registra endpoints GET
for (const t of tools) {
  server.tool(
    t.name,
    t.description,
    {
      ...(t.inputShape ?? {}),
      query: z.record(z.string(), z.any()).optional().describe("Query params para el endpoint."),
    },
    async (args: Record<string, any>) => {
      if (!API_BASE_URL) return errPayload(t.name, "API_BASE_URL no está configurado en env.");

      try {
        const { query, ...pathArgs } = args || {};
        const filledPath = fillPathTemplate(t.path, pathArgs);
        const baseUrl = `${API_BASE_URL}${filledPath}`;
        const url = addQueryParams(baseUrl, query);
        const data = await httpGetJson(url);
        return okPayload(t.name, url, data);
      } catch (e) {
        return errPayload(t.name, e);
      }
    }
  );
}

// =======================
// Schemas comunes de filtrado
// =======================
const filterOps = z.enum(["eq", "neq", "gt", "gte", "lt", "lte", "contains", "startsWith", "endsWith", "in", "exists"]);

const filterSchemaBase = {
  query: z.record(z.string(), z.any()).optional().describe("Query params opcionales antes de filtrar local."),
  arrayPath: z.string().optional().describe("Ruta al array dentro del JSON (si viene envuelto)."),
  filters: z
    .array(z.object({ field: z.string(), op: filterOps, value: z.any().optional() }))
    .optional()
    .describe("Filtros AND."),
  search: z.object({ text: z.string().min(1), fields: z.array(z.string()).min(1) }).optional(),
  sort: z.object({ field: z.string(), direction: z.enum(["asc", "desc"]).default("asc") }).optional(),
  page: z.number().int().min(1).optional().default(1),
  pageSize: z.number().int().min(1).max(500).optional().default(50),
  select: z.array(z.string()).optional(),
  limit: z.number().int().min(1).max(5000).optional(),
};

// =======================
// 1) filter_json (genérico)
// =======================
server.tool(
  "filter_json",
  "Filtra/ordena/pagina un JSON (respuesta de otra tool).",
  { input: z.any(), ...filterSchemaBase },
  async (args: any) => {
    try {
      const result = applyFilterPipeline({
        input: args?.input,
        arrayPath: args?.arrayPath,
        filters: args?.filters,
        search: args?.search,
        sort: args?.sort,
        page: args?.page,
        pageSize: args?.pageSize,
        select: args?.select,
        limit: args?.limit,
      });
      return okPayload("filter_json", "local://filter_json", result);
    } catch (e) {
      return errPayload("filter_json", e);
    }
  }
);

// =======================
// 2) Helpers: construir filtros "por tabla" (con campos SQL)
// =======================
const personPresetSchema = {
  id: z.union([z.string(), z.number()]).optional(),
  ci: z.string().optional(),
  nombre: z.string().optional(),
  apellidos: z.string().optional(),
  email: z.string().optional(),
  telefono: z.string().optional().describe("Busca en telf1 o telf2 o tel_referencia"),
  sexo: z.string().optional(),
  sangre: z.string().optional(),
  nacimiento: z.string().optional(),
  residencia: z.string().optional(),
  perfil: z.string().optional(),
  fecha_nacimiento_from: z.string().optional().describe("YYYY-MM-DD"),
  fecha_nacimiento_to: z.string().optional().describe("YYYY-MM-DD"),
  q: z.string().optional().describe("Búsqueda libre (nombre/apellidos/ci/email/teléfonos/dirección)"),
};

function buildPersonPresetFilters(preset: any): { filters: FilterSpec[]; search?: { text: string; fields: string[] } } {
  const filters: FilterSpec[] = [];

  if (preset?.id != null) filters.push({ field: "id", op: "eq", value: preset.id });
  if (preset?.ci) filters.push({ field: "ci", op: "contains", value: preset.ci });
  if (preset?.nombre) filters.push({ field: "nombre", op: "contains", value: preset.nombre });
  if (preset?.apellidos) filters.push({ field: "apellidos", op: "contains", value: preset.apellidos });
  if (preset?.email) filters.push({ field: "email", op: "contains", value: preset.email });
  if (preset?.sexo) filters.push({ field: "sexo", op: "eq", value: preset.sexo });
  if (preset?.sangre) filters.push({ field: "sangre", op: "eq", value: preset.sangre });
  if (preset?.nacimiento) filters.push({ field: "nacimiento", op: "contains", value: preset.nacimiento });
  if (preset?.residencia) filters.push({ field: "residencia", op: "contains", value: preset.residencia });
  if (preset?.perfil) filters.push({ field: "perfil", op: "eq", value: preset.perfil });

  if (preset?.fecha_nacimiento_from) filters.push({ field: "fecha_nacimiento", op: "gte", value: preset.fecha_nacimiento_from });
  if (preset?.fecha_nacimiento_to) filters.push({ field: "fecha_nacimiento", op: "lte", value: preset.fecha_nacimiento_to });

  let search: { text: string; fields: string[] } | undefined;

  if (preset?.telefono) {
    search = { text: preset.telefono, fields: ["telf1", "telf2", "tel_referencia"] };
  }

  if (preset?.q) {
    const qSearchFields = ["nombre", "apellidos", "ci", "email", "telf1", "telf2", "direccion", "referencia", "tel_referencia", "ocupacion", "residencia", "nacimiento"];
    if (search) {
      search = { text: preset.q, fields: Array.from(new Set([...search.fields, ...qSearchFields])) };
    } else {
      search = { text: preset.q, fields: qSearchFields };
    }
  }

  return { filters, search };
}

const citasPresetSchema = {
  id: z.union([z.string(), z.number()]).optional(),
  patient_id: z.union([z.string(), z.number()]).optional(),
  estado: z.string().optional(),
  tipo_evento: z.string().optional(),
  motivo: z.string().optional(),
  fecha_from: z.string().optional().describe("YYYY-MM-DD o ISO"),
  fecha_to: z.string().optional().describe("YYYY-MM-DD o ISO"),
  q: z.string().optional().describe("Busca en motivo/comentarios/estado/tipo_evento"),
};

function buildCitasPresetFilters(preset: any) {
  const filters: FilterSpec[] = [];
  let search: { text: string; fields: string[] } | undefined;

  if (preset?.id != null) filters.push({ field: "id", op: "eq", value: preset.id });
  if (preset?.patient_id != null) filters.push({ field: "patient_id", op: "eq", value: preset.patient_id });
  if (preset?.estado) filters.push({ field: "estado", op: "eq", value: preset.estado });
  if (preset?.tipo_evento) filters.push({ field: "tipo_evento", op: "eq", value: preset.tipo_evento });
  if (preset?.motivo) filters.push({ field: "motivo", op: "contains", value: preset.motivo });

  if (preset?.fecha_from) filters.push({ field: "fecha", op: "gte", value: preset.fecha_from });
  if (preset?.fecha_to) filters.push({ field: "fecha", op: "lte", value: preset.fecha_to });

  if (preset?.q) search = { text: preset.q, fields: ["motivo", "comentarios", "estado", "tipo_evento"] };
  return { filters, search };
}

const visitasPresetSchema = {
  id: z.union([z.string(), z.number()]).optional(),
  patient_id: z.union([z.string(), z.number()]).optional(),
  cita_id: z.union([z.string(), z.number()]).optional(),
  motivo: z.string().optional(),
  diagnostico: z.string().optional(),
  lugar_atencion: z.string().optional(),
  created_from: z.string().optional(),
  created_to: z.string().optional(),
  q: z.string().optional().describe("Busca en motivo/diagnostico/examen_fisico/comentarios/conducta"),
};

function buildVisitasPresetFilters(preset: any) {
  const filters: FilterSpec[] = [];
  let search: { text: string; fields: string[] } | undefined;

  if (preset?.id != null) filters.push({ field: "id", op: "eq", value: preset.id });
  if (preset?.patient_id != null) filters.push({ field: "patient_id", op: "eq", value: preset.patient_id });
  if (preset?.cita_id != null) filters.push({ field: "cita_id", op: "eq", value: preset.cita_id });

  if (preset?.motivo) filters.push({ field: "motivo", op: "contains", value: preset.motivo });
  if (preset?.diagnostico) filters.push({ field: "diagnostico", op: "contains", value: preset.diagnostico });
  if (preset?.lugar_atencion) filters.push({ field: "lugar_atencion", op: "contains", value: preset.lugar_atencion });

  if (preset?.created_from) filters.push({ field: "created_at", op: "gte", value: preset.created_from });
  if (preset?.created_to) filters.push({ field: "created_at", op: "lte", value: preset.created_to });

  if (preset?.q) search = { text: preset.q, fields: ["motivo", "diagnostico", "examen_fisico", "comentarios", "conducta", "desglose_motivo"] };
  return { filters, search };
}

const antecedentsPresetSchema = {
  id: z.union([z.string(), z.number()]).optional(),
  patient_id: z.union([z.string(), z.number()]).optional(),
  hta: z.boolean().optional(),
  dm: z.boolean().optional(),
  alergias: z.boolean().optional(),
  quirurgicos: z.boolean().optional(),
  fuma: z.boolean().optional(),
  alcohol: z.boolean().optional(),
  donante: z.boolean().optional(),
  q: z.string().optional().describe("Busca en descripciones y notas"),
};

function buildAntecedentsPresetFilters(preset: any) {
  const filters: FilterSpec[] = [];
  let search: { text: string; fields: string[] } | undefined;

  if (preset?.id != null) filters.push({ field: "id", op: "eq", value: preset.id });
  if (preset?.patient_id != null) filters.push({ field: "patient_id", op: "eq", value: preset.patient_id });

  const boolTo01 = (b: boolean) => (b ? 1 : 0);

  if (preset?.hta != null) filters.push({ field: "hta", op: "eq", value: boolTo01(preset.hta) });
  if (preset?.dm != null) filters.push({ field: "dm", op: "eq", value: boolTo01(preset.dm) });
  if (preset?.alergias != null) filters.push({ field: "alergias", op: "eq", value: boolTo01(preset.alergias) });
  if (preset?.quirurgicos != null) filters.push({ field: "quirurgicos", op: "eq", value: boolTo01(preset.quirurgicos) });
  if (preset?.fuma != null) filters.push({ field: "fuma", op: "eq", value: boolTo01(preset.fuma) });
  if (preset?.alcohol != null) filters.push({ field: "alcohol", op: "eq", value: boolTo01(preset.alcohol) });
  if (preset?.donante != null) filters.push({ field: "donante", op: "eq", value: boolTo01(preset.donante) });

  if (preset?.q) {
    search = {
      text: preset.q,
      fields: [
        "enfermedades_description",
        "otros_description",
        "alergias_description",
        "medicacion_description",
        "otros_med_description",
        "quirurgicos_description",
        "antecedentesfamiliares",
        "antecedentespersonales",
        "notas_legado",
      ],
    };
  }
  return { filters, search };
}

// =======================
// 3) Tools "de dominio" con presets + fallback filters/manual
// =======================
server.tool(
  "person_filter",
  "Filtra personas (tabla persons). Soporta preset (campos reales) + filters/search manual.",
  { preset: z.object(personPresetSchema).optional(), ...filterSchemaBase },
  async (args: any) => {
    if (!API_BASE_URL) return errPayload("person_filter", "API_BASE_URL no está configurado en env.");
    try {
      const url = addQueryParams(`${API_BASE_URL}/v1/person`, args?.query);
      const data = await httpGetJson(url);

      const presetBuilt = args?.preset ? buildPersonPresetFilters(args.preset) : { filters: [], search: undefined };

      const result = applyFilterPipeline({
        input: data,
        arrayPath: args?.arrayPath,
        filters: [...(presetBuilt.filters || []), ...(args?.filters || [])],
        search: args?.search ?? presetBuilt.search,
        sort: args?.sort,
        page: args?.page,
        pageSize: args?.pageSize,
        select: args?.select,
        limit: args?.limit,
      });

      return okPayload("person_filter", url, result);
    } catch (e) {
      return errPayload("person_filter", e);
    }
  }
);

server.tool(
  "citas_filter",
  "Filtra citas (tabla citas). Puedes pasar preset o filtros manuales. Si envías patient_id, usa /v1/citas/{patient_id}.",
  { preset: z.object(citasPresetSchema).optional(), patient_id: z.union([z.string(), z.number()]).optional(), ...filterSchemaBase },
  async (args: any) => {
    if (!API_BASE_URL) return errPayload("citas_filter", "API_BASE_URL no está configurado en env.");
    try {
      const patientId = args?.patient_id ?? args?.preset?.patient_id;
      const base = patientId != null ? `${API_BASE_URL}/v1/citas/${encodeURIComponent(String(patientId))}` : `${API_BASE_URL}/v1/citas`;
      const url = addQueryParams(base, args?.query);
      const data = await httpGetJson(url);

      const presetBuilt = args?.preset ? buildCitasPresetFilters(args.preset) : { filters: [], search: undefined };

      const result = applyFilterPipeline({
        input: data,
        arrayPath: args?.arrayPath,
        filters: [...(presetBuilt.filters || []), ...(args?.filters || [])],
        search: args?.search ?? presetBuilt.search,
        sort: args?.sort,
        page: args?.page,
        pageSize: args?.pageSize,
        select: args?.select,
        limit: args?.limit,
      });

      return okPayload("citas_filter", url, result);
    } catch (e) {
      return errPayload("citas_filter", e);
    }
  }
);

server.tool(
  "visitas_filter",
  "Filtra visitas (tabla visitas). mode=by_patient o by_cita, o preset con patient_id/cita_id.",
  {
    mode: z.enum(["by_patient", "by_cita"]).optional(),
    patientId: z.union([z.string(), z.number()]).optional(),
    citaId: z.union([z.string(), z.number()]).optional(),
    preset: z.object(visitasPresetSchema).optional(),
    ...filterSchemaBase,
  },
  async (args: any) => {
    if (!API_BASE_URL) return errPayload("visitas_filter", "API_BASE_URL no está configurado en env.");
    try {
      const preset = args?.preset;

      const mode = args?.mode ?? (preset?.patient_id != null ? "by_patient" : preset?.cita_id != null ? "by_cita" : undefined);
      if (!mode) throw new Error("visitas_filter: define mode o preset.patient_id / preset.cita_id");

      const patientId = args?.patientId ?? preset?.patient_id;
      const citaId = args?.citaId ?? preset?.cita_id;

      let baseUrl = "";
      if (mode === "by_patient") {
        if (patientId == null) throw new Error("visitas_filter: falta patientId para mode=by_patient");
        baseUrl = `${API_BASE_URL}/v1/visitas/patient/${encodeURIComponent(String(patientId))}`;
      } else {
        if (citaId == null) throw new Error("visitas_filter: falta citaId para mode=by_cita");
        baseUrl = `${API_BASE_URL}/v1/visitas/${encodeURIComponent(String(citaId))}`;
      }

      const url = addQueryParams(baseUrl, args?.query);
      const data = await httpGetJson(url);

      const presetBuilt = preset ? buildVisitasPresetFilters(preset) : { filters: [], search: undefined };

      const result = applyFilterPipeline({
        input: data,
        arrayPath: args?.arrayPath,
        filters: [...(presetBuilt.filters || []), ...(args?.filters || [])],
        search: args?.search ?? presetBuilt.search,
        sort: args?.sort,
        page: args?.page,
        pageSize: args?.pageSize,
        select: args?.select,
        limit: args?.limit,
      });

      return okPayload("visitas_filter", url, result);
    } catch (e) {
      return errPayload("visitas_filter", e);
    }
  }
);

server.tool(
  "antecedents_filter",
  "Filtra antecedentes (tabla antecedents). Usa /v1/antecedents/surgical como listado disponible y filtra local.",
  { preset: z.object(antecedentsPresetSchema).optional(), ...filterSchemaBase },
  async (args: any) => {
    if (!API_BASE_URL) return errPayload("antecedents_filter", "API_BASE_URL no está configurado en env.");
    try {
      const url = addQueryParams(`${API_BASE_URL}/v1/antecedents/surgical`, args?.query);
      const data = await httpGetJson(url);

      const presetBuilt = args?.preset ? buildAntecedentsPresetFilters(args.preset) : { filters: [], search: undefined };

      const result = applyFilterPipeline({
        input: data,
        arrayPath: args?.arrayPath,
        filters: [...(presetBuilt.filters || []), ...(args?.filters || [])],
        search: args?.search ?? presetBuilt.search,
        sort: args?.sort,
        page: args?.page,
        pageSize: args?.pageSize,
        select: args?.select,
        limit: args?.limit,
      });

      return okPayload("antecedents_filter", url, result);
    } catch (e) {
      return errPayload("antecedents_filter", e);
    }
  }
);

// =======================
// 4) Tool ORQUESTADOR: clinic_bundle
// =======================
server.tool(
  "clinic_bundle",
  "Trae y filtra varias entidades (person/patient/citas/visitas/antecedents) en una sola llamada. Ideal para preguntas complejas.",
  {
    patientId: z.union([z.string(), z.number()]).optional(),
    personId: z.union([z.string(), z.number()]).optional(),

    include: z.array(z.enum(["person", "patient", "citas", "visitas", "antecedents"])).optional().default(["person", "patient", "citas", "visitas", "antecedents"]),

    person: z.object({ preset: z.object(personPresetSchema).optional(), ...filterSchemaBase }).optional(),
    citas: z.object({ preset: z.object(citasPresetSchema).optional(), ...filterSchemaBase }).optional(),
    visitas: z.object({ preset: z.object(visitasPresetSchema).optional(), mode: z.enum(["by_patient", "by_cita"]).optional(), ...filterSchemaBase }).optional(),
    antecedents: z.object({ preset: z.object(antecedentsPresetSchema).optional(), ...filterSchemaBase }).optional(),

    maxPerSection: z.number().int().min(1).max(500).optional().default(200),
  },
  async (args: any) => {
    if (!API_BASE_URL) return errPayload("clinic_bundle", "API_BASE_URL no está configurado en env.");

    try {
      const include: string[] = args?.include || ["person", "patient", "citas", "visitas", "antecedents"];
      const maxPerSection = args?.maxPerSection ?? 200;

      const patientId = args?.patientId;
      const personId = args?.personId;

      const out: any = { patientId, personId, sections: {} };

      if (include.includes("patient") && patientId != null) {
        const url = `${API_BASE_URL}/v1/patient/${encodeURIComponent(String(patientId))}`;
        const data = await httpGetJson(url);
        out.sections.patient = { url, data };
      }

      if (include.includes("person")) {
        let pid = personId;

        if (pid == null && out.sections.patient?.data) {
          const p = out.sections.patient.data;
          pid = p?.person_id ?? p?.personId ?? p?.person?.id ?? p?.persona?.id;
        }

        if (pid != null) {
          const url = `${API_BASE_URL}/v1/person/${encodeURIComponent(String(pid))}`;
          const data = await httpGetJson(url);
          out.sections.person = { url, data };
        } else {
          out.sections.person = { warning: "No personId disponible (pasa personId o asegúrate que patient_get devuelva person_id)." };
        }
      }

      if (include.includes("citas")) {
        const cfg = args?.citas || {};
        const pPreset = cfg?.preset || {};
        const effectivePatient = pPreset?.patient_id ?? patientId;

        const base = effectivePatient != null ? `${API_BASE_URL}/v1/citas/${encodeURIComponent(String(effectivePatient))}` : `${API_BASE_URL}/v1/citas`;

        const url = addQueryParams(base, cfg?.query);
        const data = await httpGetJson(url);

        const presetBuilt = cfg?.preset ? buildCitasPresetFilters(cfg.preset) : { filters: [], search: undefined };
        const result = applyFilterPipeline({
          input: data,
          arrayPath: cfg?.arrayPath,
          filters: [...(presetBuilt.filters || []), ...(cfg?.filters || [])],
          search: cfg?.search ?? presetBuilt.search,
          sort: cfg?.sort,
          page: cfg?.page,
          pageSize: Math.min(cfg?.pageSize ?? 50, maxPerSection),
          select: cfg?.select,
          limit: cfg?.limit ?? maxPerSection,
        });

        out.sections.citas = { url, ...result };
      }

      if (include.includes("visitas")) {
        const cfg = args?.visitas || {};
        const preset = cfg?.preset || {};

        const mode = cfg?.mode ?? (preset?.patient_id != null || patientId != null ? "by_patient" : preset?.cita_id != null ? "by_cita" : undefined);

        if (!mode) {
          out.sections.visitas = { warning: "No se pudo determinar mode. Pasa visitas.mode o visitas.preset.patient_id/cita_id." };
        } else {
          const effectivePatient = preset?.patient_id ?? patientId;
          const effectiveCita = preset?.cita_id;

          const base = mode === "by_patient" ? `${API_BASE_URL}/v1/visitas/patient/${encodeURIComponent(String(effectivePatient))}` : `${API_BASE_URL}/v1/visitas/${encodeURIComponent(String(effectiveCita))}`;

          const url = addQueryParams(base, cfg?.query);
          const data = await httpGetJson(url);

          const presetBuilt = cfg?.preset ? buildVisitasPresetFilters(cfg.preset) : { filters: [], search: undefined };
          const result = applyFilterPipeline({
            input: data,
            arrayPath: cfg?.arrayPath,
            filters: [...(presetBuilt.filters || []), ...(cfg?.filters || [])],
            search: cfg?.search ?? presetBuilt.search,
            sort: cfg?.sort,
            page: cfg?.page,
            pageSize: Math.min(cfg?.pageSize ?? 50, maxPerSection),
            select: cfg?.select,
            limit: cfg?.limit ?? maxPerSection,
          });

          out.sections.visitas = { url, ...result, mode };
        }
      }

      if (include.includes("antecedents")) {
        const cfg = args?.antecedents || {};
        const presetBuilt = cfg?.preset ? buildAntecedentsPresetFilters(cfg.preset) : { filters: [], search: undefined };

        if (patientId != null && cfg?.preset?.patient_id == null) {
          presetBuilt.filters.unshift({ field: "patient_id", op: "eq", value: patientId });
        }

        const url = addQueryParams(`${API_BASE_URL}/v1/antecedents/surgical`, cfg?.query);
        const data = await httpGetJson(url);

        const result = applyFilterPipeline({
          input: data,
          arrayPath: cfg?.arrayPath,
          filters: [...(presetBuilt.filters || []), ...(cfg?.filters || [])],
          search: cfg?.search ?? presetBuilt.search,
          sort: cfg?.sort,
          page: cfg?.page,
          pageSize: Math.min(cfg?.pageSize ?? 50, maxPerSection),
          select: cfg?.select,
          limit: cfg?.limit ?? maxPerSection,
        });

        out.sections.antecedents = { url, ...result };
      }

      return okPayload("clinic_bundle", "local://clinic_bundle", out);
    } catch (e) {
      return errPayload("clinic_bundle", e);
    }
  }
);

// =======================
// Start
// =======================
async function main() {
  try {
    const transport = new StdioServerTransport();
    await server.connect(transport);

    console.error("[clinic-api-get] running via stdio");
    console.error(`[clinic-api-get] API_BASE_URL=${API_BASE_URL || "(missing)"}`);
    console.error(`[clinic-api-get] HTTP_TIMEOUT_MS=${HTTP_TIMEOUT_MS}`);
    console.error(`[clinic-api-get] AUTH=${API_TOKEN ? "enabled" : "disabled"}`);

    await new Promise<void>(() => {});
  } catch (err) {
    console.error("[clinic-api-get] fatal:", err);
    process.exit(1);
  }
}
main();
