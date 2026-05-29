import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { API_BASE_URL } from "../config.js";
import { httpGetJson } from "../http.js";
import { applyFilterPipeline, getByPath, pickArray } from "../filters/pipeline.js";
import { filterSchemaBase } from "../filters/schema.js";
import { errPayload, okPayload } from "../payload.js";

function normalizeCitaRow(cita: any) {
  return {
    cita_id: getByPath(cita, "id") ?? getByPath(cita, "cita_id"),
    fecha: getByPath(cita, "fecha") ?? null,
    hora_inicio: getByPath(cita, "hora_inicio") ?? null,
    hora_fin: getByPath(cita, "hora_fin") ?? null,
    estado: getByPath(cita, "estado") ?? null,
    tipo_evento: getByPath(cita, "tipo_evento") ?? null,
    motivo: getByPath(cita, "motivo") ?? null,
    comentarios: getByPath(cita, "comentarios") ?? null,
    patient_id:
      getByPath(cita, "patient_id") ??
      getByPath(cita, "patient.id") ??
      getByPath(cita, "patient.persona.id") ??
      getByPath(cita, "persona.id") ??
      null,
    patient_name:
      getByPath(cita, "patient.persona.nombre") ??
      getByPath(cita, "patient.nombre") ??
      getByPath(cita, "persona.nombre") ??
      getByPath(cita, "paciente.persona.nombre") ??
      getByPath(cita, "paciente.nombre") ??
      null,
  };
}

function extractPatientNameFromPatient(patient: any) {
  return (
    getByPath(patient, "persona.nombre") ??
    getByPath(patient, "nombre") ??
    getByPath(patient, "apellidos") ??
    getByPath(patient, "persona.apellidos") ??
    null
  );
}

async function fetchPatientName(patientId: string | number) {
  try {
    const patient = await httpGetJson(`${API_BASE_URL}/v1/patient/${encodeURIComponent(String(patientId))}`);
    return extractPatientNameFromPatient(patient);
  } catch {
    return null;
  }
}

export function registerCitaByIdTool(server: McpServer) {
  server.tool(
    "cita_by_id",
    "Busca una cita por su ID y devuelve la cita con el paciente asociado. Útil para preguntas como 'cual es el paciente de la cita 52'.",
    {
      id: z.union([z.string(), z.number()]),
      ...filterSchemaBase,
    },
    async (args: any) => {
      if (!API_BASE_URL) return errPayload("cita_by_id", "API_BASE_URL no está configurado en env.");

      try {
        const data = await httpGetJson(`${API_BASE_URL}/v1/citas`);
        const rows = pickArray(data);
        const targetId = String(args?.id);
        const match = rows.find((row: any) => String(getByPath(row, "id") ?? getByPath(row, "cita_id")) === targetId);

        const normalized = match ? [normalizeCitaRow(match)] : [];
        if (normalized.length && !normalized[0].patient_name && normalized[0].patient_id != null) {
          normalized[0].patient_name = await fetchPatientName(normalized[0].patient_id);
        }
        const result = applyFilterPipeline({
          input: normalized,
          filters: args?.filters || [],
          search: args?.search,
          sort: args?.sort,
          page: args?.page,
          pageSize: args?.pageSize,
          select: args?.select,
          limit: args?.limit,
        });

        return okPayload("cita_by_id", `${API_BASE_URL}/v1/citas`, {
          ...result,
          context: match
            ? {
                cita_id: getByPath(match, "id") ?? targetId,
                patient_id: getByPath(match, "patient_id") ?? getByPath(match, "patient.id") ?? null,
                patient_name:
                  normalized[0]?.patient_name ??
                  getByPath(match, "patient.persona.nombre") ??
                  getByPath(match, "patient.nombre") ??
                  getByPath(match, "persona.nombre") ??
                  null,
              }
            : {
                cita_id: targetId,
                note: "No se encontró una cita con ese ID.",
              },
        });
      } catch (e) {
        return errPayload("cita_by_id", e);
      }
    },
  );
}
