import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { API_BASE_URL } from "../config.js";
import { addQueryParams, httpGetJson } from "../http.js";
import { applyFilterPipeline } from "../filters/pipeline.js";
import { filterSchemaBase } from "../filters/schema.js";
import { errPayload, okPayload } from "../payload.js";
import { buildVisitasPresetFilters, visitasPresetSchema } from "../presets/visitas.js";

export function registerVisitasTools(server: McpServer) {
  server.tool(
    "visitas_filter",
    "Filtra visitas (tabla visitas). mode=by_patient o by_cita, o preset con patient_id/cita_id.",
    {
      mode: z.enum(["by_patient", "by_cita"]).optional(),
      patientId: z.union([z.string(), z.number()]).optional(),
      citaId: z.union([z.string(), z.number()]).optional(),
      preset: z.object(visitasPresetSchema).optional(),
      ...filterSchemaBase,
    },
    async (args: any) => {
      if (!API_BASE_URL) return errPayload("visitas_filter", "API_BASE_URL no está configurado en env.");
      try {
        const preset = args?.preset;

        const mode =
          args?.mode ??
          (preset?.patient_id != null ? "by_patient" : preset?.cita_id != null ? "by_cita" : undefined);
        if (!mode) throw new Error("visitas_filter: define mode o preset.patient_id / preset.cita_id");

        const patientId = args?.patientId ?? preset?.patient_id;
        const citaId = args?.citaId ?? preset?.cita_id;

        let baseUrl = "";
        if (mode === "by_patient") {
          if (patientId == null) throw new Error("visitas_filter: falta patientId para mode=by_patient");
          baseUrl = `${API_BASE_URL}/v1/visitas/patient/${encodeURIComponent(String(patientId))}`;
        } else {
          if (citaId == null) throw new Error("visitas_filter: falta citaId para mode=by_cita");
          baseUrl = `${API_BASE_URL}/v1/visitas/${encodeURIComponent(String(citaId))}`;
        }

        const url = addQueryParams(baseUrl, args?.query);
        const data = await httpGetJson(url);

        const presetBuilt = preset ? buildVisitasPresetFilters(preset) : { filters: [], search: undefined };

        const result = applyFilterPipeline({
          input: data,
          arrayPath: args?.arrayPath,
          filters: [...(presetBuilt.filters || []), ...(args?.filters || [])],
          search: args?.search ?? presetBuilt.search,
          sort: args?.sort,
          page: args?.page,
          pageSize: args?.pageSize,
          select: args?.select,
          limit: args?.limit,
        });

        return okPayload("visitas_filter", url, result);
      } catch (e) {
        return errPayload("visitas_filter", e);
      }
    },
  );
}
