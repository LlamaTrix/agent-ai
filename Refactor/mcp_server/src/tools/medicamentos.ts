import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { API_BASE_URL } from "../config.js";
import { addQueryParams, httpGetJson } from "../http.js";
import { applyFilterPipeline } from "../filters/pipeline.js";
import { filterSchemaBase } from "../filters/schema.js";
import { errPayload, okPayload } from "../payload.js";

export function registerMedicamentosTools(server: McpServer) {
  server.tool(
    "medicamentos",
    "Consulta el catálogo de medicamentos/recetas únicas desde /v1/recetasMedicamentos. Devuelve nombres únicos y permite filtrar localmente si la API retorna una lista amplia.",
    {
      ...filterSchemaBase,
      categoria: z.string().optional().describe("Filtro libre si el backend devuelve objetos con categoría o tipo."),
    },
    async (args: any) => {
      if (!API_BASE_URL) return errPayload("medicamentos", "API_BASE_URL no está configurado en env.");

      try {
        const url = addQueryParams(`${API_BASE_URL}/v1/recetasMedicamentos`, args?.query);
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

        return okPayload("medicamentos", url, result);
      } catch (e) {
        return errPayload("medicamentos", e);
      }
    },
  );
}
