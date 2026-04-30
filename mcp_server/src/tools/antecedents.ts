import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { API_BASE_URL } from "../config.js";
import { addQueryParams, httpGetJson } from "../http.js";
import { applyFilterPipeline } from "../filters/pipeline.js";
import { filterSchemaBase } from "../filters/schema.js";
import { errPayload, okPayload } from "../payload.js";
import { antecedentsPresetSchema, buildAntecedentsPresetFilters } from "../presets/antecedents.js";

export function registerAntecedentsTools(server: McpServer) {
  server.tool(
    "antecedents_filter",
    "Filtra antecedentes (tabla antecedents). Usa /v1/antecedents/surgical como listado disponible y filtra local.",
    { preset: z.object(antecedentsPresetSchema).optional(), ...filterSchemaBase },
    async (args: any) => {
      if (!API_BASE_URL) return errPayload("antecedents_filter", "API_BASE_URL no está configurado en env.");
      try {
        const url = addQueryParams(`${API_BASE_URL}/v1/antecedents/surgical`, args?.query);
        const data = await httpGetJson(url);

        const presetBuilt = args?.preset
          ? buildAntecedentsPresetFilters(args.preset)
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

        return okPayload("antecedents_filter", url, result);
      } catch (e) {
        return errPayload("antecedents_filter", e);
      }
    },
  );
}
