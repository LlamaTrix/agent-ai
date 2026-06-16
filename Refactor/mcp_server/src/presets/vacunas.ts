import { z } from "zod";
import type { FilterSpec } from "../filters/pipeline.js";

// Vacunas = vacunas APLICADAS (registrovacunas). /v1/registros-vacunas devuelve
// cada aplicación aplanada con el nombre de la vacuna y del paciente embebidos:
// vacuna, paciente, nombre, apellidos, sexo, fecha_aplicacion, edad, id_persons.
export const vacunasPresetSchema = {
  vacuna: z.string().optional().describe("Nombre de la vacuna (contains, ej. 'Rotavirus')"),
  paciente: z.string().optional().describe("Nombre del paciente (busca en paciente/nombre/apellidos)"),
  id_persons: z.union([z.string(), z.number()]).optional(),
  mes: z.string().optional().describe("YYYY-MM (fecha de aplicación)"),
  fecha_from: z.string().optional().describe("YYYY-MM-DD o ISO"),
  fecha_to: z.string().optional().describe("YYYY-MM-DD o ISO"),
};

export function buildVacunasPresetFilters(preset: any) {
  const filters: FilterSpec[] = [];
  let search: { text: string; fields: string[] } | undefined;

  if (preset?.vacuna) filters.push({ field: "vacuna", op: "contains", value: String(preset.vacuna) });
  if (preset?.id_persons != null) filters.push({ field: "id_persons", op: "eq", value: preset.id_persons });

  if (preset?.mes) filters.push({ field: "fecha_aplicacion", op: "contains", value: preset.mes });
  if (preset?.fecha_from) filters.push({ field: "fecha_aplicacion", op: "gte", value: preset.fecha_from });
  if (preset?.fecha_to) filters.push({ field: "fecha_aplicacion", op: "lte", value: preset.fecha_to });

  if (preset?.paciente) search = { text: preset.paciente, fields: ["paciente", "nombre", "apellidos"] };
  return { filters, search };
}
