import { z } from "zod";
import type { FilterSpec } from "../filters/pipeline.js";

export const patientPresetSchema = {
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

export function buildPatientPresetFilters(
  preset: any,
): { filters: FilterSpec[]; search?: { text: string; fields: string[] } } {
  const filters: FilterSpec[] = [];

  if (preset?.id != null) filters.push({ field: "id", op: "eq", value: preset.id });
  if (preset?.ci) filters.push({ field: "persona.ci", op: "contains", value: preset.ci });
  if (preset?.nombre) filters.push({ field: "persona.nombre", op: "contains", value: preset.nombre });
  if (preset?.apellidos) filters.push({ field: "persona.apellidos", op: "contains", value: preset.apellidos });
  if (preset?.email) filters.push({ field: "persona.email", op: "contains", value: preset.email });
  if (preset?.sexo) filters.push({ field: "persona.sexo", op: "eq", value: preset.sexo });
  if (preset?.sangre) filters.push({ field: "persona.sangre", op: "eq", value: preset.sangre });
  if (preset?.nacimiento) filters.push({ field: "persona.nacimiento", op: "contains", value: preset.nacimiento });
  if (preset?.residencia) filters.push({ field: "persona.residencia", op: "contains", value: preset.residencia });
  if (preset?.perfil) filters.push({ field: "persona.perfil", op: "eq", value: preset.perfil });

  if (preset?.fecha_nacimiento_from)
    filters.push({ field: "persona.fecha_nacimiento", op: "gte", value: preset.fecha_nacimiento_from });
  if (preset?.fecha_nacimiento_to)
    filters.push({ field: "persona.fecha_nacimiento", op: "lte", value: preset.fecha_nacimiento_to });

  let search: { text: string; fields: string[] } | undefined;

  if (preset?.telefono) {
    search = { text: preset.telefono, fields: ["persona.telf1", "persona.telf2", "persona.tel_referencia"] };
  }

  if (preset?.q) {
    const qSearchFields = [
      "persona.nombre",
      "persona.apellidos",
      "persona.ci",
      "persona.email",
      "persona.telf1",
      "persona.telf2",
      "persona.tel_referencia",
      "persona.residencia",
    ];
    search = { text: preset.q, fields: qSearchFields };
  }

  return { filters, search };
}