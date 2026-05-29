import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { API_BASE_URL } from "../config.js";
import { addQueryParams, httpGetJson } from "../http.js";
import { applyFilterPipeline, getByPath, pickArray } from "../filters/pipeline.js";
import { filterSchemaBase } from "../filters/schema.js";
import { errPayload, okPayload } from "../payload.js";

function extractPatientIdFromCita(cita: any) {
  return (
    getByPath(cita, "patient_id") ??
    getByPath(cita, "patientId") ??
    getByPath(cita, "patient.id") ??
    getByPath(cita, "patient.persona.id") ??
    getByPath(cita, "persona.id") ??
    getByPath(cita, "paciente.id") ??
    getByPath(cita, "paciente.persona.id")
  );
}

function extractPatientNameFromCita(cita: any) {
  return (
    getByPath(cita, "patient.persona.nombre") ??
    getByPath(cita, "patient.nombre") ??
    getByPath(cita, "persona.nombre") ??
    getByPath(cita, "paciente.persona.nombre") ??
    getByPath(cita, "paciente.nombre") ??
    getByPath(cita, "nombre")
  );
}

async function fetchCitaContext(citaId: string | number) {
  const url = `${API_BASE_URL}/v1/citas`;
  const data = await httpGetJson(url);
  const rows = pickArray(data);
  const match = rows.find((row: any) => {
    const rowId = getByPath(row, "id") ?? getByPath(row, "cita_id");
    return String(rowId) === String(citaId);
  });

  if (!match) return null;

  return {
    citaId: match.id ?? match.cita_id ?? citaId,
    patientId: extractPatientIdFromCita(match),
    patientName: extractPatientNameFromCita(match),
  };
}

function normalizeOdontogramaRows(input: any, route: string) {
  const sourceRows = pickArray(input);
  const flatRows: any[] = [];

  for (const row of sourceRows) {
    if (!row || typeof row !== "object") {
      flatRows.push(row);
      continue;
    }

    const cita = getByPath(row, "cita") ?? null;
    const piezas = getByPath(row, "piezas");

    if (Array.isArray(piezas)) {
      for (const pieza of piezas) {
        flatRows.push({
          odontograma_id: getByPath(pieza, "odontograma_id") ?? getByPath(pieza, "id"),
          cita_id: row.cita_id ?? getByPath(row, "cita_id"),
          cita_fecha: row.fecha ?? getByPath(row, "fecha"),
          cita_tipo_evento: row.tipo_evento ?? getByPath(row, "tipo_evento"),
          patient_id: row.patient_id ?? getByPath(row, "patient_id"),
          patient_name: row.patient_name ?? getByPath(row, "patient_name"),
          diente: getByPath(pieza, "diente"),
          diagnostico: getByPath(pieza, "diagnostico"),
          tratamiento: getByPath(pieza, "tratamiento"),
          costo: getByPath(pieza, "costo"),
          notas: getByPath(pieza, "notas"),
          route,
        });
      }
      continue;
    }

    flatRows.push({
      odontograma_id: row.id ?? getByPath(row, "odontograma_id"),
      cita_id: row.cita_id ?? getByPath(row, "cita_id"),
      cita_fecha: getByPath(cita, "fecha") ?? getByPath(row, "fecha"),
      cita_tipo_evento: getByPath(cita, "tipo_evento") ?? getByPath(row, "tipo_evento"),
      patient_id: getByPath(cita, "patient_id") ?? getByPath(row, "patient_id"),
      patient_name:
        getByPath(cita, "patient.persona.nombre") ??
        getByPath(cita, "patient.nombre") ??
        getByPath(cita, "persona.nombre") ??
        getByPath(row, "patient_name") ??
        getByPath(row, "nombre"),
      diente: row.diente,
      diagnostico: row.diagnostico,
      tratamiento: row.tratamiento,
      costo: row.costo,
      route,
    });
  }

  return flatRows;
}

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
        const normalizedRows = normalizeOdontogramaRows(data, route);

        const result = applyFilterPipeline({
          input: normalizedRows,
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
        const errorMessage = (e as any)?.message ?? String(e);

        if (args?.cita_id != null && errorMessage.includes("Attempt to read property \"odontograma\" on null")) {
          try {
            const citaContext = await fetchCitaContext(args.cita_id);

            if (!citaContext) {
              return okPayload("odontogramas", `${API_BASE_URL}/v1/odontogramas/cita/${encodeURIComponent(String(args.cita_id))}`, {
                items: [],
                total: 0,
                returned: 0,
                context: {
                  cita_id: args.cita_id,
                  note: "No se encontró información de la cita para resolver el paciente.",
                },
              });
            }

            if (citaContext.patientId == null || String(citaContext.patientId).trim() === "") {
              return okPayload("odontogramas", `${API_BASE_URL}/v1/odontogramas/cita/${encodeURIComponent(String(args.cita_id))}`, {
                items: [],
                total: 0,
                returned: 0,
                context: {
                  cita_id: args.cita_id,
                  patient_name: citaContext.patientName ?? null,
                  note: "La cita existe, pero no trae patient_id para recuperar el odontograma por paciente.",
                },
              });
            }

            const patientRoute = `${API_BASE_URL}/v1/odontogramas/paciente/${encodeURIComponent(String(citaContext.patientId ?? ""))}`;
            const patientData = await httpGetJson(patientRoute);
            const patientRows = normalizeOdontogramaRows(patientData, patientRoute);
            const matchingHistory = patientRows.filter((item: any) => String(getByPath(item, "cita_id") ?? getByPath(item, "id")) === String(args.cita_id));

            return okPayload("odontogramas", patientRoute, {
              items: matchingHistory,
              total: matchingHistory.length,
              returned: matchingHistory.length,
              context: {
                cita_id: args.cita_id,
                patient_id: citaContext.patientId ?? null,
                patient_name: citaContext.patientName ?? null,
                note: matchingHistory.length
                  ? "Se obtuvo el odontograma por paciente como fallback."
                  : "La cita existe, pero no se encontró odontograma asociado.",
              },
            });
          } catch (fallbackError) {
            return okPayload("odontogramas", `${API_BASE_URL}/v1/odontogramas/cita/${encodeURIComponent(String(args.cita_id))}`, {
              items: [],
              total: 0,
              returned: 0,
              context: {
                cita_id: args.cita_id,
                note: `No se pudo resolver el odontograma por cita, pero el error original fue: ${errorMessage}`,
                fallback_error: (fallbackError as any)?.message ?? String(fallbackError),
              },
            });
          }
        }

        return errPayload("odontogramas", e);
      }
    },
  );
}
