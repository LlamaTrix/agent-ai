import { z } from "zod";
import type { FilterSpec } from "../filters/pipeline.js";

export const visitasPresetSchema = {
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

export function buildVisitasPresetFilters(preset: any) {
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

  if (preset?.q)
    search = {
      text: preset.q,
      fields: ["motivo", "diagnostico", "examen_fisico", "comentarios", "conducta", "desglose_motivo"],
    };
  return { filters, search };
}
