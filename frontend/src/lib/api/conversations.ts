import { http } from "./http";
import { ENDPOINTS } from "./config";
import type {
  ConversationResponse,
  ConversationDetailResponse,
  SendMessageResponse,
  MessageResponse,
} from "./types";

export async function createConversation(title: string): Promise<ConversationResponse> {
  return http(ENDPOINTS.conversations + "/", {
    method: "POST",
    body: { title },
  });
}

export async function listConversations(params?: {
  limit?: number;
  offset?: number;
}): Promise<ConversationResponse[]> {
  const qs = new URLSearchParams();
  if (params?.limit !== undefined) qs.set("limit", String(params.limit));
  if (params?.offset !== undefined) qs.set("offset", String(params.offset));
  const path = `${ENDPOINTS.conversations}/` + (qs.toString() ? `?${qs.toString()}` : "");
  return http(path);
}

export async function getConversation(id: string): Promise<ConversationDetailResponse> {
  // Always request full state data for messages
  return http(`${ENDPOINTS.conversations}/${encodeURIComponent(id)}?include_full=true`);
}

export async function updateConversation(id: string, title: string): Promise<ConversationResponse> {
  return http(`${ENDPOINTS.conversations}/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: { title },
  });
}

export async function deleteConversation(id: string): Promise<{ status: string; conversation_id: string }> {
  return http(`${ENDPOINTS.conversations}/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function clearConversation(id: string): Promise<{ status: string; conversation_id: string }> {
  return http(`${ENDPOINTS.conversations}/${encodeURIComponent(id)}/clear`, { method: "PUT" });
}

export async function sendMessage(
  id: string,
  content: string,
  filePaths?: string[]
): Promise<SendMessageResponse> {
  return http(`${ENDPOINTS.conversations}/${encodeURIComponent(id)}/messages`, {
    method: "POST",
    body: { content, file_paths: filePaths },
  });
}

export async function getMessages(id: string, limit?: number): Promise<MessageResponse[]> {
  const qs = new URLSearchParams();
  if (limit !== undefined) qs.set("limit", String(limit));
  const url = `${ENDPOINTS.conversations}/${encodeURIComponent(id)}/messages` + (qs.toString() ? `?${qs.toString()}` : "");
  return http(url);
}

export async function sendClarification(
  id: string,
  feedback: string
): Promise<SendMessageResponse> {
  return http(`${ENDPOINTS.conversations}/${encodeURIComponent(id)}/clarification`, {
    method: "POST",
    body: { feedback },
  });
}


