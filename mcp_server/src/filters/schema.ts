import { z } from "zod";

export const filterOps = z.enum([
  "eq",
  "neq",
  "gt",
  "gte",
  "lt",
  "lte",
  "contains",
  "startsWith",
  "endsWith",
  "in",
  "exists",
]);

export const filterSchemaBase = {
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
