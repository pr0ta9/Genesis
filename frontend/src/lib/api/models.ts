import { http } from "./http";
import { ENDPOINTS } from "./config";
import type { ModelResponse } from "./types";

export async function listModels(): Promise<ModelResponse[]> {
  return http(ENDPOINTS.models + "/");
}

export async function getCurrentModel(): Promise<{ current: string; fallback?: string | null }> {
  return http(ENDPOINTS.models + "/current");
}



