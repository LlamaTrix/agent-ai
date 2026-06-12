import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { API_BASE_URL } from "../config.js";
import { addQueryParams, httpGetJson } from "../http.js";
import { applyFilterPipeline } from "../filters/pipeline.js";
import { filterSchemaBase } from "../filters/schema.js";
import { errPayload, okPayload } from "../payload.js";
import { buildRecetasPresetFilters, recetasPresetSchema } from "../presets/recetas.js";

export function registerRecetasTools(server: McpServer) {
  server.tool(
    "recetas_filter",
    "Filtra recetas/medicamentos prescritos. Con preset.patient_id usa /v1/recetas/paciente/{id}; " +
      "si no, /v1/recetas (todas). Filtra por nombre del medicamento, presentación y mes/fecha de la cita.",
    {
      preset: z.object(recetasPresetSchema).optional(),
      patient_id: z.union([z.string(), z.number()]).optional(),
      ...filterSchemaBase,
    },
    async (args: any) => {
      if (!API_BASE_URL) return errPayload("recetas_filter", "API_BASE_URL no está configurado en env.");
      try {
        const patientId = args?.patient_id ?? args?.preset?.patient_id;
        const base =
          patientId != null
            ? `${API_BASE_URL}/v1/recetas/paciente/${encodeURIComponent(String(patientId))}`
            : `${API_BASE_URL}/v1/recetas`;

        const url = addQueryParams(base, args?.query);
        const data = await httpGetJson(url);

        const presetBuilt = args?.preset
          ? buildRecetasPresetFilters(args.preset)
          : { filters: [], search: undefined };

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

        return okPayload("recetas_filter", url, result);
      } catch (e) {
        return errPayload("recetas_filter", e);
      }
    },
  );
}
