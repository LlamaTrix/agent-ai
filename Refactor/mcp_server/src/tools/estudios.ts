import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { API_BASE_URL } from "../config.js";
import { addQueryParams, httpGetJson } from "../http.js";
import { applyFilterPipeline } from "../filters/pipeline.js";
import { filterSchemaBase } from "../filters/schema.js";
import { errPayload, okPayload } from "../payload.js";
import { buildEstudiosPresetFilters, estudiosPresetSchema } from "../presets/estudios.js";

export function registerEstudiosTools(server: McpServer) {
  server.tool(
    "estudios_filter",
    "Filtra estudios/ÓRDENES (Laboratorio, Análisis de Gabinete, Gabinete Cardiológico). " +
      "Con preset.patient_id usa /v1/estudios/paciente/{id}; con preset.cita_id usa /v1/estudios/cita/{id}; " +
      "si no, /v1/estudios (todos). Filtra por tipo, nombre y mes/fecha de la cita.",
    {
      preset: z.object(estudiosPresetSchema).optional(),
      patient_id: z.union([z.string(), z.number()]).optional(),
      cita_id: z.union([z.string(), z.number()]).optional(),
      ...filterSchemaBase,
    },
    async (args: any) => {
      if (!API_BASE_URL) return errPayload("estudios_filter", "API_BASE_URL no está configurado en env.");
      try {
        const patientId = args?.patient_id ?? args?.preset?.patient_id;
        const citaId = args?.cita_id ?? args?.preset?.cita_id;

        let base = `${API_BASE_URL}/v1/estudios`;
        if (patientId != null) {
          base = `${API_BASE_URL}/v1/estudios/paciente/${encodeURIComponent(String(patientId))}`;
        } else if (citaId != null) {
          base = `${API_BASE_URL}/v1/estudios/cita/${encodeURIComponent(String(citaId))}`;
        }

        const url = addQueryParams(base, args?.query);
        const data = await httpGetJson(url);

        const presetBuilt = args?.preset
          ? buildEstudiosPresetFilters(args.preset)
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

        return okPayload("estudios_filter", url, result);
      } catch (e) {
        return errPayload("estudios_filter", e);
      }
    },
  );
}
