import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { API_BASE_URL, API_TOKEN, HTTP_TIMEOUT_MS } from "./src/config.js";
import { registerAllTools } from "./src/tools/index.js";

const server = new McpServer({ name: "clinic-api-get", version: "1.1.0" });
registerAllTools(server);

async function main() {
  try {
    const transport = new StdioServerTransport();
    await server.connect(transport);

    console.error("[clinic-api-get] running via stdio");
    console.error(`[clinic-api-get] API_BASE_URL=${API_BASE_URL || "(missing)"}`);
    console.error(`[clinic-api-get] HTTP_TIMEOUT_MS=${HTTP_TIMEOUT_MS}`);
    console.error(`[clinic-api-get] AUTH=${API_TOKEN ? "enabled" : "disabled"}`);

    await new Promise<void>(() => {});
  } catch (err) {
    console.error("[clinic-api-get] fatal:", err);
    process.exit(1);
  }
}
main();
