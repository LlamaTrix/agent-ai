import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { API_BASE_URL } from "../config.js";
import { addQueryParams, httpGetJson } from "../http.js";
import { applyFilterPipeline } from "../filters/pipeline.js";
import { filterSchemaBase } from "../filters/schema.js";
import { errPayload, okPayload } from "../payload.js";

export function registerOdontogramasTools(server: McpServer) {
  server.tool(
    "odontogramas",
    "Consulta odontogramas. Sin args trae todos; con cita_id usa /v1/odontogramas/cita/{cita_id}; con patient_id usa /v1/odontogramas/paciente/{patient_id}.",
    {
      cita_id: z.union([z.string(), z.number()]).optional(),
      patient_id: z.union([z.string(), z.number()]).optional(),
      ...filterSchemaBase,
    },
    async (args: any) => {
      if (!API_BASE_URL) return errPayload("odontogramas", "API_BASE_URL no está configurado en env.");

      try {
        const route =
          args?.cita_id != null
            ? `/v1/odontogramas/cita/${encodeURIComponent(String(args.cita_id))}`
            : args?.patient_id != null
              ? `/v1/odontogramas/paciente/${encodeURIComponent(String(args.patient_id))}`
              : "/v1/odontogramas";

        const url = addQueryParams(`${API_BASE_URL}${route}`, args?.query);
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

        return okPayload("odontogramas", url, result);
      } catch (e) {
        return errPayload("odontogramas", e);
      }
    },
  );
}
