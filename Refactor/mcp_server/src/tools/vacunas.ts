import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { API_BASE_URL } from "../config.js";
import { addQueryParams, httpGetJson } from "../http.js";
import { applyFilterPipeline } from "../filters/pipeline.js";
import { filterSchemaBase } from "../filters/schema.js";
import { errPayload, okPayload } from "../payload.js";
import { buildVacunasPresetFilters, vacunasPresetSchema } from "../presets/vacunas.js";

export function registerVacunasTools(server: McpServer) {
  server.tool(
    "vacunas_filter",
    "Filtra vacunas APLICADAS (registrovacunas) desde /v1/registros-vacunas. Cada " +
      "fila es una aplicación con el nombre de la vacuna y del paciente embebidos " +
      "(vacuna, paciente, nombre, apellidos, sexo, fecha_aplicacion, edad, id_persons). " +
      "Usa preset.vacuna para filtrar por nombre de vacuna (contains, ej. 'Rotavirus') " +
      "y preset.paciente para buscar las vacunas de un paciente. NO hay datos de " +
      "vencimiento/calendario (no se puede saber si una vacuna está 'vencida').",
    {
      preset: z.object(vacunasPresetSchema).optional(),
      ...filterSchemaBase,
    },
    async (args: any) => {
      if (!API_BASE_URL) return errPayload("vacunas_filter", "API_BASE_URL no está configurado en env.");
      try {
        const base = `${API_BASE_URL}/v1/vacunas-aplicadas`;
        const url = addQueryParams(base, args?.query);
        const data = await httpGetJson(url);

        const presetBuilt = args?.preset
          ? buildVacunasPresetFilters(args.preset)
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

        return okPayload("vacunas_filter", url, result);
      } catch (e) {
        return errPayload("vacunas_filter", e);
      }
    },
  );
}
