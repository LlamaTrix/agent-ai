import { z } from "zod";
import type { FilterSpec } from "../filters/pipeline.js";

// Recetas = prescripciones (medicamento, presentación, cantidad, instrucciones).
// /v1/recetas devuelve cada receta con su visita → cita (visita.cita.fecha) y el
// paciente (visita.patient.persona.*) embebidos.
export const recetasPresetSchema = {
  patient_id: z.union([z.string(), z.number()]).optional(),
  visita_id: z.union([z.string(), z.number()]).optional(),
  nombre: z.string().optional().describe("Nombre del medicamento"),
  presentacion: z.string().optional().describe("Presentación (jarabe, tabletas, etc.)"),
  mes: z.string().optional().describe("YYYY-MM (fecha de la cita)"),
  fecha_from: z.string().optional().describe("YYYY-MM-DD o ISO"),
  fecha_to: z.string().optional().describe("YYYY-MM-DD o ISO"),
  q: z.string().optional().describe("Busca en nombre/presentacion/instrucciones"),
};

export function buildRecetasPresetFilters(preset: any) {
  const filters: FilterSpec[] = [];
  let search: { text: string; fields: string[] } | undefined;

  if (preset?.nombre) filters.push({ field: "nombre", op: "contains", value: preset.nombre });
  if (preset?.presentacion) filters.push({ field: "presentacion", op: "contains", value: preset.presentacion });
  if (preset?.visita_id != null) filters.push({ field: "visita_id", op: "eq", value: preset.visita_id });

  // La fecha de la receta = fecha de la cita de su visita (visita.cita.fecha).
  if (preset?.mes) filters.push({ field: "visita.cita.fecha", op: "contains", value: preset.mes });
  if (preset?.fecha_from) filters.push({ field: "visita.cita.fecha", op: "gte", value: preset.fecha_from });
  if (preset?.fecha_to) filters.push({ field: "visita.cita.fecha", op: "lte", value: preset.fecha_to });

  if (preset?.q) search = { text: preset.q, fields: ["nombre", "presentacion", "instrucciones"] };
  return { filters, search };
}
