import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { API_BASE_URL } from "../config.js";
import { addQueryParams, httpGetJson } from "../http.js";
import { applyFilterPipeline } from "../filters/pipeline.js";
import { filterSchemaBase } from "../filters/schema.js";
import { errPayload, okPayload } from "../payload.js";

export function registerPaymentsTools(server: McpServer) {
  server.tool(
    "payments_filter",
    "Filtra pagos (/v1/payments). Soporta filtros/search/sort/paginacion local sobre la respuesta del API.",
    { ...filterSchemaBase },
    async (args: any) => {
      if (!API_BASE_URL) return errPayload("payments_filter", "API_BASE_URL no estÃ¡ configurado en env.");
      try {
        const base = `${API_BASE_URL}/v1/payments`;
        const url = addQueryParams(base, args?.query);
        const data = await httpGetJson(url);

        const result = applyFilterPipeline({
          input: data,
          arrayPath: args?.arrayPath,
          filters: args?.filters || [],
          search: args?.search,
          sort: args?.sort,
          page: args?.page,
          pageSize: args?.pageSize,
          select: args?.select,
          limit: args?.limit,
        });

        return okPayload("payments_filter", url, result);
      } catch (e) {
        return errPayload("payments_filter", e);
      }
    },
  );
}

