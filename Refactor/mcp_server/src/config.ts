export const API_BASE_URL = (process.env.API_BASE_URL || "").replace(/\/+$/, "");
export const API_TOKEN = (process.env.API_TOKEN || process.env.API_AUTH || "").trim();
export const HTTP_TIMEOUT_MS = Number(process.env.HTTP_TIMEOUT_MS || "30000");
