import { z } from "zod";
import type { FilterSpec } from "../filters/pipeline.js";

// "Órdenes" en el sistema = estudios: Laboratorio + Análisis de Gabinete +
// Gabinete Cardiológico. /v1/estudios devuelve cada estudio con su `tipo` y la
// `cita` embebida (cita.fecha, cita.patient.persona.*).
export const estudiosPresetSchema = {
  patient_id: z.union([z.string(), z.number()]).optional(),
  cita_id: z.union([z.string(), z.number()]).optional(),
  tipo: z.string().optional().describe("Laboratorio | Analisis de Gabinete | Gabinete Cardiologico"),
  nombre: z.string().optional().describe("Nombre del estudio (gabinete/cardiológico, ej. Ecocardiograma)"),
  mes: z.string().optional().describe("YYYY-MM para filtrar por mes de la cita"),
  fecha_from: z.string().optional().describe("YYYY-MM-DD o ISO"),
  fecha_to: z.string().optional().describe("YYYY-MM-DD o ISO"),
  q: z.string().optional().describe("Busca en tipo/nombre/descripcion"),
};

export function buildEstudiosPresetFilters(preset: any) {
  const filters: FilterSpec[] = [];
  let search: { text: string; fields: string[] } | undefined;

  if (preset?.tipo) filters.push({ field: "tipo", op: "eq", value: preset.tipo });
  if (preset?.nombre) filters.push({ field: "nombre", op: "contains", value: preset.nombre });
  if (preset?.cita_id != null) filters.push({ field: "cita_id", op: "eq", value: preset.cita_id });

  // La fecha del estudio = fecha de su cita (cita.fecha).
  if (preset?.mes) filters.push({ field: "cita.fecha", op: "contains", value: preset.mes });
  if (preset?.fecha_from) filters.push({ field: "cita.fecha", op: "gte", value: preset.fecha_from });
  if (preset?.fecha_to) filters.push({ field: "cita.fecha", op: "lte", value: preset.fecha_to });

  if (preset?.q) search = { text: preset.q, fields: ["tipo", "nombre", "descripcion"] };
  return { filters, search };
}
