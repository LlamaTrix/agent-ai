import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { registerGenericGetTools } from "./generic-get.js";
import { registerFilterJsonTool } from "./filter-json.js";
import { registerPersonTools } from "./person.js";
import { registerCitasTools } from "./citas.js";
import { registerVisitasTools } from "./visitas.js";
import { registerAntecedentsTools } from "./antecedents.js";
import { registerBundleTool } from "./bundle.js";
import { registerPatientFilterTools } from "./patient.js";
import { registerPaymentsTools } from "./payments.js";

export function registerAllTools(server: McpServer) {
  registerGenericGetTools(server);
  registerFilterJsonTool(server);
  registerPersonTools(server);
  registerCitasTools(server);
  registerVisitasTools(server);
  registerAntecedentsTools(server);
  registerBundleTool(server);
  registerPatientFilterTools(server);
  registerPaymentsTools(server);
}
