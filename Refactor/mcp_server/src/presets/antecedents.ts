import { z } from "zod";
import type { FilterSpec } from "../filters/pipeline.js";

export const antecedentsPresetSchema = {
  id: z.union([z.string(), z.number()]).optional(),
  patient_id: z.union([z.string(), z.number()]).optional(),
  sangre: z.string().optional().describe("Tipo de sangre exacto: O+, A-, AB+, etc."),
  peso_min: z.number().optional(),
  peso_max: z.number().optional(),
  altura_min: z.number().optional(),
  altura_max: z.number().optional(),
  hta: z.boolean().optional().describe("Hipertension arterial"),
  dm: z.boolean().optional().describe("Diabetes mellitus"),
  alergias: z.boolean().optional(),
  alergias_tipo: z.string().optional().describe("Tipo de alergia (medicamentos, alimentos, etc)"),
  quirurgicos: z.boolean().optional(),
  fuma: z.boolean().optional().describe("Fuma actualmente?"),
  alcohol: z.boolean().optional().describe("Consume alcohol?"),
  donante: z.boolean().optional(),
  enfermedades_cronicas: z.string().optional().describe("Enfermedad cronica especifica"),
  medicacion_actual: z.string().optional().describe("Medicamento especifico"),
  antecedentes_familiares: z.string().optional().describe("Enfermedad en familia"),
  q: z.string().optional().describe("Busca en descripciones y notas"),
};

export function buildAntecedentsPresetFilters(preset: any) {
  const filters: FilterSpec[] = [];
  let search: { text: string; fields: string[] } | undefined;

  if (preset?.id != null) filters.push({ field: "id", op: "eq", value: preset.id });
  if (preset?.patient_id != null) filters.push({ field: "patient_id", op: "eq", value: preset.patient_id });

  if (preset?.sangre) filters.push({ field: "sangre", op: "eq", value: preset.sangre });
  if (preset?.peso_min != null) filters.push({ field: "peso", op: "gte", value: preset.peso_min });
  if (preset?.peso_max != null) filters.push({ field: "peso", op: "lte", value: preset.peso_max });
  if (preset?.altura_min != null) filters.push({ field: "altura", op: "gte", value: preset.altura_min });
  if (preset?.altura_max != null) filters.push({ field: "altura", op: "lte", value: preset.altura_max });

  const boolTo01 = (b: boolean) => (b ? 1 : 0);

  if (preset?.hta != null) filters.push({ field: "hta", op: "eq", value: boolTo01(preset.hta) });
  if (preset?.dm != null) filters.push({ field: "dm", op: "eq", value: boolTo01(preset.dm) });
  if (preset?.alergias != null) filters.push({ field: "alergias", op: "eq", value: boolTo01(preset.alergias) });
  if (preset?.quirurgicos != null) filters.push({ field: "quirurgicos", op: "eq", value: boolTo01(preset.quirurgicos) });
  if (preset?.fuma != null) filters.push({ field: "fuma", op: "eq", value: boolTo01(preset.fuma) });
  if (preset?.alcohol != null) filters.push({ field: "alcohol", op: "eq", value: boolTo01(preset.alcohol) });
  if (preset?.donante != null) filters.push({ field: "donante", op: "eq", value: boolTo01(preset.donante) });
  if (preset?.alergias_tipo) filters.push({ field: "alergias_description", op: "contains", value: preset.alergias_tipo });
  if (preset?.enfermedades_cronicas) filters.push({ field: "enfermedades_description", op: "contains", value: preset.enfermedades_cronicas });
  if (preset?.medicacion_actual) filters.push({ field: "medicacion_description", op: "contains", value: preset.medicacion_actual });
  if (preset?.antecedentes_familiares) filters.push({ field: "antecedentesfamiliares", op: "contains", value: preset.antecedentes_familiares });

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
