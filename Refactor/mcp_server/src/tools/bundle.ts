import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { API_BASE_URL } from "../config.js";
import { addQueryParams, httpGetJson } from "../http.js";
import { applyFilterPipeline } from "../filters/pipeline.js";
import { filterSchemaBase } from "../filters/schema.js";
import { errPayload, okPayload } from "../payload.js";
import { personPresetSchema } from "../presets/person.js";
import { buildCitasPresetFilters, citasPresetSchema } from "../presets/citas.js";
import { buildVisitasPresetFilters, visitasPresetSchema } from "../presets/visitas.js";
import { antecedentsPresetSchema, buildAntecedentsPresetFilters } from "../presets/antecedents.js";

export function registerBundleTool(server: McpServer) {
  server.tool(
    "clinic_bundle",
    "Trae y filtra varias entidades (person/patient/citas/visitas/antecedents) en una sola llamada. Ideal para preguntas complejas.",
    {
      patientId: z.union([z.string(), z.number()]).optional(),
      personId: z.union([z.string(), z.number()]).optional(),

      include: z
        .array(z.enum(["person", "patient", "citas", "visitas", "antecedents"]))
        .optional()
        .default(["person", "patient", "citas", "visitas", "antecedents"]),

      person: z.object({ preset: z.object(personPresetSchema).optional(), ...filterSchemaBase }).optional(),
      citas: z.object({ preset: z.object(citasPresetSchema).optional(), ...filterSchemaBase }).optional(),
      visitas: z
        .object({
          preset: z.object(visitasPresetSchema).optional(),
          mode: z.enum(["by_patient", "by_cita"]).optional(),
          ...filterSchemaBase,
        })
        .optional(),
      antecedents: z.object({ preset: z.object(antecedentsPresetSchema).optional(), ...filterSchemaBase }).optional(),

      maxPerSection: z.number().int().min(1).max(500).optional().default(200),
    },
    async (args: any) => {
      if (!API_BASE_URL) return errPayload("clinic_bundle", "API_BASE_URL no está configurado en env.");

      try {
        const include: string[] = args?.include || ["person", "patient", "citas", "visitas", "antecedents"];
        const maxPerSection = args?.maxPerSection ?? 200;

        const patientId = args?.patientId;
        const personId = args?.personId;

        const out: any = { patientId, personId, sections: {} };

        if (include.includes("patient") && patientId != null) {
          const url = `${API_BASE_URL}/v1/patient/${encodeURIComponent(String(patientId))}`;
          const data = await httpGetJson(url);
          out.sections.patient = { url, data };
        }

        if (include.includes("person")) {
          let pid = personId;

          if (pid == null && out.sections.patient?.data) {
            const p = out.sections.patient.data;
            pid = p?.person_id ?? p?.personId ?? p?.person?.id ?? p?.persona?.id;
          }

          if (pid != null) {
            const url = `${API_BASE_URL}/v1/person/${encodeURIComponent(String(pid))}`;
            const data = await httpGetJson(url);
            out.sections.person = { url, data };
          } else {
            out.sections.person = {
              warning: "No personId disponible (pasa personId o asegúrate que patient_get devuelva person_id).",
            };
          }
        }

        if (include.includes("citas")) {
          const cfg = args?.citas || {};
          const pPreset = cfg?.preset || {};
          const effectivePatient = pPreset?.patient_id ?? patientId;

          const base =
            effectivePatient != null
              ? `${API_BASE_URL}/v1/citas/${encodeURIComponent(String(effectivePatient))}`
              : `${API_BASE_URL}/v1/citas`;

          const url = addQueryParams(base, cfg?.query);
          const data = await httpGetJson(url);

          const presetBuilt = cfg?.preset ? buildCitasPresetFilters(cfg.preset) : { filters: [], search: undefined };
          const result = applyFilterPipeline({
            input: data,
            arrayPath: cfg?.arrayPath,
            filters: [...(presetBuilt.filters || []), ...(cfg?.filters || [])],
            search: cfg?.search ?? presetBuilt.search,
            sort: cfg?.sort,
            page: cfg?.page,
            pageSize: Math.min(cfg?.pageSize ?? 50, maxPerSection),
            select: cfg?.select,
            limit: cfg?.limit ?? maxPerSection,
          });

          out.sections.citas = { url, ...result };
        }

        if (include.includes("visitas")) {
          const cfg = args?.visitas || {};
          const preset = cfg?.preset || {};

          const mode =
            cfg?.mode ??
            (preset?.patient_id != null || patientId != null
              ? "by_patient"
              : preset?.cita_id != null
                ? "by_cita"
                : undefined);

          if (!mode) {
            out.sections.visitas = {
              warning: "No se pudo determinar mode. Pasa visitas.mode o visitas.preset.patient_id/cita_id.",
            };
          } else {
            const effectivePatient = preset?.patient_id ?? patientId;
            const effectiveCita = preset?.cita_id;

            const base =
              mode === "by_patient"
                ? `${API_BASE_URL}/v1/visitas/patient/${encodeURIComponent(String(effectivePatient))}`
                : `${API_BASE_URL}/v1/visitas/${encodeURIComponent(String(effectiveCita))}`;

            const url = addQueryParams(base, cfg?.query);
            const data = await httpGetJson(url);

            const presetBuilt = cfg?.preset
              ? buildVisitasPresetFilters(cfg.preset)
              : { filters: [], search: undefined };
            const result = applyFilterPipeline({
              input: data,
              arrayPath: cfg?.arrayPath,
              filters: [...(presetBuilt.filters || []), ...(cfg?.filters || [])],
              search: cfg?.search ?? presetBuilt.search,
              sort: cfg?.sort,
              page: cfg?.page,
              pageSize: Math.min(cfg?.pageSize ?? 50, maxPerSection),
              select: cfg?.select,
              limit: cfg?.limit ?? maxPerSection,
            });

            out.sections.visitas = { url, ...result, mode };
          }
        }

        if (include.includes("antecedents")) {
          const cfg = args?.antecedents || {};
          const presetBuilt = cfg?.preset
            ? buildAntecedentsPresetFilters(cfg.preset)
            : { filters: [], search: undefined };

          if (patientId != null && cfg?.preset?.patient_id == null) {
            presetBuilt.filters.unshift({ field: "patient_id", op: "eq", value: patientId });
          }

          const url = addQueryParams(`${API_BASE_URL}/v1/antecedents/surgical`, cfg?.query);
          const data = await httpGetJson(url);

          const result = applyFilterPipeline({
            input: data,
            arrayPath: cfg?.arrayPath,
            filters: [...(presetBuilt.filters || []), ...(cfg?.filters || [])],
            search: cfg?.search ?? presetBuilt.search,
            sort: cfg?.sort,
            page: cfg?.page,
            pageSize: Math.min(cfg?.pageSize ?? 50, maxPerSection),
            select: cfg?.select,
            limit: cfg?.limit ?? maxPerSection,
          });

          out.sections.antecedents = { url, ...result };
        }

        return okPayload("clinic_bundle", "local://clinic_bundle", out);
      } catch (e) {
        return errPayload("clinic_bundle", e);
      }
    },
  );
}
