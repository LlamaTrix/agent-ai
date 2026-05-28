export type FilterSpec = { field: string; op: string; value?: any };

const INTERNAL_FIELDS = new Set([
  "created_at", "updated_at", "deleted_at",
  "num_seguro", "empresa_seg", "ref_medica",
  "pivot",
]);

export function stripInternalFields(row: any): any {
  if (!row || typeof row !== "object" || Array.isArray(row)) return row;
  const out: any = {};
  for (const [k, v] of Object.entries(row)) {
    if (INTERNAL_FIELDS.has(k)) continue;
    out[k] = typeof v === "object" && v !== null && !Array.isArray(v)
      ? stripInternalFields(v)
      : v;
  }
  return out;
}

export function getByPath(obj: any, path: string) {
  if (!path) return undefined;
  const parts = path.split(".").filter(Boolean);
  let cur = obj;
  for (const p of parts) {
    if (cur == null) return undefined;
    cur = cur[p];
  }
  return cur;
}

export function pickArray(input: any, arrayPath?: string) {
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

export function toComparable(v: any) {
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

function isMeaningfulBirthdate(value: any) {
  if (value == null) return false;

  if (value instanceof Date) {
    return !Number.isNaN(value.getTime()) && value.getTime() <= Date.now();
  }

  if (typeof value !== "string") return false;

  const s = value.trim();
  if (!s) return false;

  const normalized = s.slice(0, 10);
  if (normalized === "0000-00-00") {
    return false;
  }

  const ms = Date.parse(s);
  if (Number.isNaN(ms)) return false;

  const parsed = new Date(ms);
  if (parsed.getTime() > Date.now()) return false;
  if (parsed.getUTCFullYear() < 1900) return false;

  return true;
}

export function compareOp(a: any, op: string, b: any) {
  const A = toComparable(a);
  const B = toComparable(b);
  switch (op) {
    case "eq":
      if (typeof a === "string" && typeof b === "string")
        return a.trim().toLowerCase() === b.trim().toLowerCase();
      return A === B;
    case "neq":
      if (typeof a === "string" && typeof b === "string")
        return a.trim().toLowerCase() !== b.trim().toLowerCase();
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
    case "not_exists":
      return !(a !== undefined && a !== null && String(a) !== "");
    case "exists":
      const exists = a !== undefined && a !== null && String(a) !== "";
      if (b === false || b === "false" || b === 0) return !exists;
      return exists;
    default:
      throw new Error(`Unsupported operator: ${op}`);
  }
}

export function applyFilterPipeline(params: {
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
  let out = arr.slice();

  // Add derived helper fields to simplify filters for common checks
  for (const item of out) {
    try {
      const t1 = getByPath(item, "persona.telf1") ?? getByPath(item, "telf1");
      const t2 = getByPath(item, "persona.telf2") ?? getByPath(item, "telf2");
      const tref = getByPath(item, "persona.tel_referencia") ?? getByPath(item, "tel_referencia");
      const tel = getByPath(item, "persona.telefono") ?? getByPath(item, "telefono");
      item.__has_phone = Boolean(
        (t1 && String(t1).trim()) ||
        (t2 && String(t2).trim()) ||
        (tref && String(tref).trim()) ||
        (tel && String(tel).trim()),
      );

      const numSeguro = getByPath(item, "persona.num_seguro") ?? getByPath(item, "num_seguro");
      const empresaSeg = getByPath(item, "persona.empresa_seg") ?? getByPath(item, "empresa_seg");
      item.__has_seguro = Boolean(
        (numSeguro && String(numSeguro).trim()) ||
        (empresaSeg && String(empresaSeg).trim()),
      );

      const estadoCivil = getByPath(item, "persona.estado_civil") ?? getByPath(item, "estado_civil");
      item.__estado_civil = estadoCivil ?? null;

      const birthdate = getByPath(item, "persona.fecha_nacimiento") ?? getByPath(item, "fecha_nacimiento");
      item.__has_birthdate = isMeaningfulBirthdate(birthdate);
    } catch (e) {
      // ignore derivation errors
    }
  }

out = out.filter((item: any) => {
  for (const f of filters) {

    let val: any;

    // =====================================================
    // CAMPOS DERIVADOS / INTERNOS
    // =====================================================
    if (f.field === "__has_phone") {
      val = item.__has_phone;
    }
    else if (f.field === "__has_seguro") {
      val = item.__has_seguro;
    }
    else if (f.field === "__estado_civil") {
      val = item.__estado_civil;
    }
    else if (
      (f.field === "__has_birthdate" ||
        f.field === "persona.fecha_nacimiento" ||
        f.field === "fecha_nacimiento") &&
      (f.op === "exists" || f.op === "not_exists")
    ) {
      val = item.__has_birthdate;
    }
    else {
      val = getByPath(item, f.field);
    }

    if (!compareOp(val, f.op, f.value)) {
      return false;
    }
  }

  return true;
});

  if (search?.text && Array.isArray(search.fields) && search.fields.length) {
    const q = String(search.text).toLowerCase();
    out = out.filter((item: any) =>
      search.fields.some((field: string) => {
        const v = getByPath(item, field);
        return v != null && String(v).toLowerCase().includes(q);
      }),
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

  const total = out.length;

  if (limit) out = out.slice(0, limit);

  // Si se pasa limit o pageSize grande, no paginar
  const effectivePageSize = limit ? out.length : pageSize;
  const start = (page - 1) * effectivePageSize;
  const paged = limit ? out : out.slice(start, start + effectivePageSize);

  const selectedItems =
    Array.isArray(select) && select.length
      ? paged.map((item: any) => {
          const obj: any = {};
          for (const f of select) obj[f] = getByPath(item, f);
          return obj;
        })
      : paged;

  const finalItems = selectedItems.map(stripInternalFields);

  return { total, page, pageSize, returned: finalItems.length, items: finalItems };
}
