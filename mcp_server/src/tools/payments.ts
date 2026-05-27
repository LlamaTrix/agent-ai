import { z } from "zod";
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

  server.tool(
    "payments_by_patient",
    "Pagos de un paciente (/v1/payments/{patient_id}). Opcionalmente aplica filtros/search/sort/paginacion local.",
    { patient_id: z.union([z.string(), z.number()]), ...filterSchemaBase },
    async (args: any) => {
      if (!API_BASE_URL) return errPayload("payments_by_patient", "API_BASE_URL no estÃ¡ configurado en env.");
      try {
        const patientId = args?.patient_id;
        const base = `${API_BASE_URL}/v1/payments/${encodeURIComponent(String(patientId))}`;
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

        return okPayload("payments_by_patient", url, result);
      } catch (e) {
        return errPayload("payments_by_patient", e);
      }
    },
  );
}

