import { API_TOKEN, HTTP_TIMEOUT_MS } from "./config.js";

function buildAuthHeader(token: string) {
  if (!token) return undefined;
  return token.toLowerCase().startsWith("bearer ") ? token : `Bearer ${token}`;
}

export function fillPathTemplate(path: string, params: Record<string, unknown>) {
  return path.replace(/\{([^}]+)\}/g, (_, key) => {
    const v = (params as any)[key];
    if (v === undefined || v === null || String(v).length === 0) {
      throw new Error(`Missing required path param: ${key}`);
    }
    return encodeURIComponent(String(v));
  });
}

export function addQueryParams(url: string, query?: Record<string, any>) {
  if (!query || typeof query !== "object") return url;
  const u = new URL(url);
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || String(v) === "") continue;
    if (Array.isArray(v)) for (const item of v) u.searchParams.append(k, String(item));
    else u.searchParams.set(k, String(v));
  }
  return u.toString();
}

export async function httpGetJson(url: string) {
  const headers: Record<string, string> = { Accept: "application/json" };
  const auth = buildAuthHeader(API_TOKEN);
  if (auth) headers["Authorization"] = auth;

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), HTTP_TIMEOUT_MS);

  try {
    const res = await fetch(url, { method: "GET", headers, signal: ctrl.signal });
    const text = await res.text();

    let body: any = text;
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      // keep string
    }

    if (!res.ok) {
      const msg = typeof body === "object" && body ? JSON.stringify(body) : String(body ?? "");
      throw new Error(`HTTP ${res.status} ${res.statusText}: ${msg}`);
    }
    return body;
  } catch (e: any) {
    if (e?.name === "AbortError") throw new Error(`Timeout HTTP (${HTTP_TIMEOUT_MS}ms) para: ${url}`);
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

