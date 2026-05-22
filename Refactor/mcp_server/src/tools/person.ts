import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { API_BASE_URL } from "../config.js";
import { addQueryParams, httpGetJson } from "../http.js";
import { applyFilterPipeline } from "../filters/pipeline.js";
import { filterSchemaBase } from "../filters/schema.js";
import { errPayload, okPayload } from "../payload.js";
import { buildPersonPresetFilters, personPresetSchema } from "../presets/person.js";

export function registerPersonTools(server: McpServer) {
  server.tool(
    "person_filter",
    "Filtra personas (tabla persons). Soporta preset (campos reales) + filters/search manual. Presets: tiene_telefono, tiene_seguro, num_seguro, empresa_seg, estado_civil.",
    { preset: z.object(personPresetSchema).optional(), ...filterSchemaBase },
    async (args: any) => {
      if (!API_BASE_URL) return errPayload("person_filter", "API_BASE_URL no está configurado en env.");
      try {
        const url = addQueryParams(`${API_BASE_URL}/v1/person`, args?.query);
        const data = await httpGetJson(url);

        const presetBuilt = args?.preset ? buildPersonPresetFilters(args.preset) : { filters: [], search: undefined };

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

        return okPayload("person_filter", url, result);
      } catch (e) {
        return errPayload("person_filter", e);
      }
    },
  );
}
