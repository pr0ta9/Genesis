import { http } from "./http";
import { ENDPOINTS } from "./config";
import type { StateResponse } from "./types";

export async function getState(stateUid: string, includeFull = false): Promise<StateResponse> {
  const qs = includeFull ? "?include_full=true" : "";
  return http(`${ENDPOINTS.states}/${encodeURIComponent(stateUid)}${qs}`);
}

export async function getStateByMessage(messageId: number, includeFull = false): Promise<StateResponse> {
  const qs = includeFull ? "?include_full=true" : "";
  return http(`${ENDPOINTS.states}/message/${encodeURIComponent(String(messageId))}${qs}`);
}


