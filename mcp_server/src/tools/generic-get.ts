import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { API_BASE_URL } from "../config.js";
import { addQueryParams, fillPathTemplate, httpGetJson } from "../http.js";
import { errPayload, okPayload } from "../payload.js";

type ToolDef = {
  name: string;
  description: string;
  path: string;
  inputShape?: Record<string, z.ZodTypeAny>;
};

const tools: ToolDef[] = [
  { name: "person_list", description: "GET /v1/person", path: "/v1/person" },
  { name: "person_get", description: "GET /v1/person/{id}", path: "/v1/person/{id}", inputShape: { id: z.string() } },

  { name: "patient_list", description: "GET /v1/patient", path: "/v1/patient" },
  { name: "patient_get", description: "GET /v1/patient/{id}", path: "/v1/patient/{id}", inputShape: { id: z.string() } },

  { name: "citas_list", description: "GET /v1/citas", path: "/v1/citas" },
  {
    name: "citas_by_patient",
    description: "GET /v1/citas/{patient_id}",
    path: "/v1/citas/{patient_id}",
    inputShape: { patient_id: z.string() },
  },

  {
    name: "visitas_by_patient",
    description: "GET /v1/visitas/patient/{patientId}",
    path: "/v1/visitas/patient/{patientId}",
    inputShape: { patientId: z.string() },
  },
  {
    name: "visitas_by_cita",
    description: "GET /v1/visitas/{citaId}",
    path: "/v1/visitas/{citaId}",
    inputShape: { citaId: z.string() },
  },

  { name: "antecedents_unique_surgical", description: "GET /v1/antecedents/surgical", path: "/v1/antecedents/surgical" },
  {
    name: "antecedents_get",
    description: "GET /v1/antecedents/{id}",
    path: "/v1/antecedents/{id}",
    inputShape: { id: z.string() },
  },
];

export function registerGenericGetTools(server: McpServer) {
  for (const t of tools) {
    server.tool(
      t.name,
      t.description,
      {
        ...(t.inputShape ?? {}),
        query: z.record(z.string(), z.any()).optional().describe("Query params para el endpoint."),
      },
      async (args: Record<string, any>) => {
        if (!API_BASE_URL) return errPayload(t.name, "API_BASE_URL no está configurado en env.");

        try {
          const { query, ...pathArgs } = args || {};
          const filledPath = fillPathTemplate(t.path, pathArgs);
          const baseUrl = `${API_BASE_URL}${filledPath}`;
          const url = addQueryParams(baseUrl, query);
          const data = await httpGetJson(url);
          return okPayload(t.name, url, data);
        } catch (e) {
          return errPayload(t.name, e);
        }
      },
    );
  }
}
