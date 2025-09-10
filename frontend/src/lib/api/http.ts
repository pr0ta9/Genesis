import { buildUrl } from "./config";

export type HttpMethod = "GET" | "POST" | "PUT" | "DELETE";

export interface RequestOptions<TBody = unknown> {
  method?: HttpMethod;
  body?: TBody;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

export async function http<TResponse = unknown, TBody = unknown>(
  path: string,
  options: RequestOptions<TBody> = {}
): Promise<TResponse> {
  const { method = "GET", body, headers = {}, signal } = options;
  const url = buildUrl(path);
  const isDev = typeof window !== "undefined" && process.env.NODE_ENV !== "production";

  const computedHeaders: Record<string, string> = { ...headers };
  const isFormData = typeof FormData !== "undefined" && body instanceof FormData;
  // Only set Content-Type for non-GET or when sending a body, but do NOT set it for FormData
  if ((method !== "GET" || body !== undefined) && !isFormData) {
    computedHeaders["Content-Type"] = computedHeaders["Content-Type"] || "application/json";
  }

  const init: RequestInit = {
    method,
    headers: computedHeaders,
    signal,
  };

  if (body !== undefined && method !== "GET") {
    (init as any).body = isFormData ? (body as any) : JSON.stringify(body);
  }

  if (isDev) {
    // eslint-disable-next-line no-console
    console.log("[HTTP] →", { method, url, body });
  }

  const res = await fetch(url, init).catch((err) => {
    if (isDev) {
      // eslint-disable-next-line no-console
      console.error("[HTTP] network error ←", { 
        method, 
        url, 
        error: err,
        message: err.message,
        stack: err.stack 
      });
    }
    throw err;
  });

  if (isDev) {
    // eslint-disable-next-line no-console
    console.log("[HTTP] ←", { status: res.status, url });
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    if (isDev) {
      // eslint-disable-next-line no-console
      console.error("[HTTP] error ←", { status: res.status, url, text });
    }
    throw new Error(`HTTP ${res.status}: ${text || res.statusText}`);
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) {
    return (await res.json()) as TResponse;
  }
  return (await res.text()) as unknown as TResponse;
}


