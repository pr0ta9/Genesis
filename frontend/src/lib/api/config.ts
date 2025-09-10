export const API_BASE_URL: string =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8000";

export const API_PREFIX = "/api/v1" as const;

export const ENDPOINTS = {
  health: "/",
  conversations: `${API_PREFIX}/conversations`,
  states: `${API_PREFIX}/states`,
  models: `${API_PREFIX}/models`,
  workspace: `${API_PREFIX}/workspace`,
  uploads: `${API_PREFIX}/uploads`,
  ws: (conversationId: string) =>
    `${API_BASE_URL}${API_PREFIX}/ws/${encodeURIComponent(conversationId)}`,
} as const;

export function buildUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

// Debug: Log resolved API base and example endpoints once at import time (dev only)
if (typeof window !== "undefined") {
  // Avoid noisy logs in production builds
  if (process.env.NODE_ENV !== "production") {
    try {
      // Minimal, high-signal debug output
      // eslint-disable-next-line no-console
      console.log("[API CONFIG] BASE:", API_BASE_URL);
      // eslint-disable-next-line no-console
      console.log("[API CONFIG] ENDPOINTS:", {
        health: buildUrl(ENDPOINTS.health),
        conversations: buildUrl(ENDPOINTS.conversations),
        states: buildUrl(ENDPOINTS.states),
        models: buildUrl(ENDPOINTS.models),
        workspace: buildUrl(ENDPOINTS.workspace),
      });
    } catch {
      // no-op
    }
  }
}


