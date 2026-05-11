import { z } from "zod";
import type { FilterSpec } from "../filters/pipeline.js";

export const antecedentsPresetSchema = {
  id: z.union([z.string(), z.number()]).optional(),
  patient_id: z.union([z.string(), z.number()]).optional(),
  hta: z.boolean().optional(),
  dm: z.boolean().optional(),
  alergias: z.boolean().optional(),
  quirurgicos: z.boolean().optional(),
  fuma: z.boolean().optional(),
  alcohol: z.boolean().optional(),
  donante: z.boolean().optional(),
  q: z.string().optional().describe("Busca en descripciones y notas"),
};

export function buildAntecedentsPresetFilters(preset: any) {
  const filters: FilterSpec[] = [];
  let search: { text: string; fields: string[] } | undefined;

  if (preset?.id != null) filters.push({ field: "id", op: "eq", value: preset.id });
  if (preset?.patient_id != null) filters.push({ field: "patient_id", op: "eq", value: preset.patient_id });

  const boolTo01 = (b: boolean) => (b ? 1 : 0);

  if (preset?.hta != null) filters.push({ field: "hta", op: "eq", value: boolTo01(preset.hta) });
  if (preset?.dm != null) filters.push({ field: "dm", op: "eq", value: boolTo01(preset.dm) });
  if (preset?.alergias != null) filters.push({ field: "alergias", op: "eq", value: boolTo01(preset.alergias) });
  if (preset?.quirurgicos != null) filters.push({ field: "quirurgicos", op: "eq", value: boolTo01(preset.quirurgicos) });
  if (preset?.fuma != null) filters.push({ field: "fuma", op: "eq", value: boolTo01(preset.fuma) });
  if (preset?.alcohol != null) filters.push({ field: "alcohol", op: "eq", value: boolTo01(preset.alcohol) });
  if (preset?.donante != null) filters.push({ field: "donante", op: "eq", value: boolTo01(preset.donante) });

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
