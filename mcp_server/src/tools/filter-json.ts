import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { applyFilterPipeline } from "../filters/pipeline.js";
import { filterSchemaBase } from "../filters/schema.js";
import { errPayload, okPayload } from "../payload.js";

export function registerFilterJsonTool(server: McpServer) {
  server.tool(
    "filter_json",
    "Filtra/ordena/pagina un JSON (respuesta de otra tool).",
    { input: z.any(), ...filterSchemaBase },
    async (args: any) => {
      try {
        const result = applyFilterPipeline({
          input: args?.input,
          arrayPath: args?.arrayPath,
          filters: args?.filters,
          search: args?.search,
          sort: args?.sort,
          page: args?.page,
          pageSize: args?.pageSize,
          select: args?.select,
          limit: args?.limit,
        });
        return okPayload("filter_json", "local://filter_json", result);
      } catch (e) {
        return errPayload("filter_json", e);
      }
    },
  );
}
