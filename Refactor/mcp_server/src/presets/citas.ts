import { z } from "zod";
import type { FilterSpec } from "../filters/pipeline.js";

export const citasPresetSchema = {
  id: z.union([z.string(), z.number()]).optional(),
  patient_id: z.union([z.string(), z.number()]).optional(),
  estado: z.string().optional(),
  tipo_evento: z.string().optional(),
  motivo: z.string().optional(),
  fecha_from: z.string().optional().describe("YYYY-MM-DD o ISO"),
  fecha_to: z.string().optional().describe("YYYY-MM-DD o ISO"),
  q: z.string().optional().describe("Busca en motivo/comentarios/estado/tipo_evento"),
};

export function buildCitasPresetFilters(preset: any) {
  const filters: FilterSpec[] = [];
  let search: { text: string; fields: string[] } | undefined;

  if (preset?.id != null) filters.push({ field: "id", op: "eq", value: preset.id });
  if (preset?.patient_id != null) filters.push({ field: "patient_id", op: "eq", value: preset.patient_id });
  if (preset?.estado) filters.push({ field: "estado", op: "eq", value: preset.estado });
  if (preset?.tipo_evento) filters.push({ field: "tipo_evento", op: "eq", value: preset.tipo_evento });
  if (preset?.motivo) filters.push({ field: "motivo", op: "contains", value: preset.motivo });

  if (preset?.fecha_from) filters.push({ field: "hora_inicio", op: "gte", value: preset.fecha_from });
  if (preset?.fecha_to) filters.push({ field: "hora_inicio", op: "lte", value: preset.fecha_to });

  if (preset?.q) search = { text: preset.q, fields: ["motivo", "comentarios", "estado", "tipo_evento"] };
  return { filters, search };
}
