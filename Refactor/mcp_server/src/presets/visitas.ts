import { z } from "zod";
import type { FilterSpec } from "../filters/pipeline.js";

export const visitasPresetSchema = {
  id: z.union([z.string(), z.number()]).optional(),
  patient_id: z.union([z.string(), z.number()]).optional(),
  cita_id: z.union([z.string(), z.number()]).optional(),
  motivo: z.string().optional(),
  diagnostico: z.string().optional(),
  lugar_atencion: z.string().optional(),
  medico: z.string().optional().describe("Nombre del medico que realizo la visita"),
  peso_min: z.number().optional(),
  peso_max: z.number().optional(),
  altura_min: z.number().optional(),
  altura_max: z.number().optional(),
  temperatura_min: z.number().optional(),
  temperatura_max: z.number().optional(),
  f_cardiaca_min: z.number().optional(),
  f_cardiaca_max: z.number().optional(),
  f_respiratoria_min: z.number().optional(),
  f_respiratoria_max: z.number().optional(),
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
  if (preset?.medico) filters.push({ field: "medico", op: "contains", value: preset.medico });

  if (preset?.peso_min != null) filters.push({ field: "peso", op: "gte", value: preset.peso_min });
  if (preset?.peso_max != null) filters.push({ field: "peso", op: "lte", value: preset.peso_max });
  if (preset?.altura_min != null) filters.push({ field: "altura", op: "gte", value: preset.altura_min });
  if (preset?.altura_max != null) filters.push({ field: "altura", op: "lte", value: preset.altura_max });
  if (preset?.temperatura_min != null) filters.push({ field: "temperatura", op: "gte", value: preset.temperatura_min });
  if (preset?.temperatura_max != null) filters.push({ field: "temperatura", op: "lte", value: preset.temperatura_max });
  if (preset?.f_cardiaca_min != null) filters.push({ field: "f_cardiaca", op: "gte", value: preset.f_cardiaca_min });
  if (preset?.f_cardiaca_max != null) filters.push({ field: "f_cardiaca", op: "lte", value: preset.f_cardiaca_max });
  if (preset?.f_respiratoria_min != null) filters.push({ field: "f_respiratoria", op: "gte", value: preset.f_respiratoria_min });
  if (preset?.f_respiratoria_max != null) filters.push({ field: "f_respiratoria", op: "lte", value: preset.f_respiratoria_max });

  if (preset?.created_from) filters.push({ field: "created_at", op: "gte", value: preset.created_from });
  if (preset?.created_to) filters.push({ field: "created_at", op: "lte", value: preset.created_to });

  if (preset?.q)
    search = {
      text: preset.q,
      fields: ["motivo", "diagnostico", "examen_fisico", "comentarios", "conducta", "desglose_motivo", "medico"],
    };
  return { filters, search };
}
