import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { API_BASE_URL } from "../config.js";
import { addQueryParams, httpGetJson } from "../http.js";
import { applyFilterPipeline } from "../filters/pipeline.js";
import { filterSchemaBase } from "../filters/schema.js";
import { errPayload, okPayload } from "../payload.js";
import { buildCitasPresetFilters, citasPresetSchema } from "../presets/citas.js";

export function registerCitasTools(server: McpServer) {
  server.tool(
    "citas_filter",
    "Filtra citas (tabla citas). Puedes pasar preset o filtros manuales. Si envías patient_id, usa /v1/citas/{patient_id}.",
    {
      preset: z.object(citasPresetSchema).optional(),
      patient_id: z.union([z.string(), z.number()]).optional(),
      ...filterSchemaBase,
    },
    async (args: any) => {
      if (!API_BASE_URL) return errPayload("citas_filter", "API_BASE_URL no está configurado en env.");
      try {
        const patientId = args?.patient_id ?? args?.preset?.patient_id;
        const base =
          patientId != null
            ? `${API_BASE_URL}/v1/citas/${encodeURIComponent(String(patientId))}`
            : `${API_BASE_URL}/v1/citas`;
        const url = addQueryParams(base, args?.query);
        const data = await httpGetJson(url);

        const presetBuilt = args?.preset ? buildCitasPresetFilters(args.preset) : { filters: [], search: undefined };

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

        return okPayload("citas_filter", url, result);
      } catch (e) {
        return errPayload("citas_filter", e);
      }
    },
  );
}
