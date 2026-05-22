import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { API_BASE_URL } from "../config.js";
import { addQueryParams, httpGetJson } from "../http.js";
import { applyFilterPipeline } from "../filters/pipeline.js";
import { filterSchemaBase } from "../filters/schema.js";
import { errPayload, okPayload } from "../payload.js";
import { buildPatientPresetFilters, patientPresetSchema } from "../presets/patient.js";

export function registerPatientFilterTools(server: McpServer) {
  server.tool(
    "patient_filter",
    "Filtra pacientes (/v1/patient). Soporta preset (campos de persona anidados) + filters/search manual. Presets: tiene_telefono, tiene_seguro, num_seguro, empresa_seg, estado_civil.",
    { preset: z.object(patientPresetSchema).optional(), ...filterSchemaBase },
    async (args: any) => {
      if (!API_BASE_URL) return errPayload("patient_filter", "API_BASE_URL no está configurado en env.");
      try {
        const url = addQueryParams(`${API_BASE_URL}/v1/patient`, args?.query);
        const data = await httpGetJson(url);

        const presetBuilt = args?.preset ? buildPatientPresetFilters(args.preset) : { filters: [], search: undefined };

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

        return okPayload("patient_filter", url, result);
      } catch (e) {
        return errPayload("patient_filter", e);
      }
    },
  );
}