import { ENDPOINTS } from "../api/config";

export type BackendEvent =
  | { event: "state_update"; timestamp: string; data: any; frontend_message_id?: string }
  | { event: "reasoning"; timestamp: string; data: any; frontend_message_id?: string }
  | { event: "error"; timestamp: string; data: any; frontend_message_id?: string }
  | { event: "execution_event"; timestamp: string; data: any; frontend_message_id?: string }
  | { type: "state_checkpoint"; node: string; state_uid: string; fields: string[]; timestamp: string }
  | { type: "complete"; result: any; frontend_message_id?: string };

export interface WSOptions {
  onOpen?: () => void;
  onClose?: (ev: CloseEvent) => void;
  onError?: (ev: Event) => void;
  onEvent?: (ev: BackendEvent) => void;
}

export class ConversationSocket {
  public ws?: WebSocket; // Make public for direct access
  private readonly conversationId: string;
  private opts: WSOptions;

  constructor(conversationId: string, opts: WSOptions = {}) {
    this.conversationId = conversationId;
    this.opts = opts;
  }

  connect(): void {
    const url = ENDPOINTS.ws(this.conversationId).replace(/^http/, "ws");
    const isDev = typeof window !== "undefined" && process.env.NODE_ENV !== "production";
    if (isDev) {
      // eslint-disable-next-line no-console
      console.log("[WS] ▶ connect", { url, conversationId: this.conversationId });
    }
    const ws = new WebSocket(url);
    // Ensure handlers are set before assigning ws
    ws.onopen = () => {
      if (isDev) {
        // eslint-disable-next-line no-console
        console.log("[WS] ◀ open", { url });
      }
      this.opts.onOpen?.();
    };
    ws.onclose = (e) => {
      if (isDev) {
        // eslint-disable-next-line no-console
        console.log("[WS] ◀ close", { url, code: e.code, reason: e.reason, wasClean: e.wasClean });
      }
      try { this.opts.onClose?.(e); } catch {}
    };
    ws.onerror = (e) => {
      if (isDev) {
        // eslint-disable-next-line no-console
        console.error("[WS] ◀ error", { url, event: e });
      }
      try { this.opts.onError?.(e); } catch {}
    };
    ws.onmessage = (msg) => {
      try {
        const data = JSON.parse(String(msg.data));
        if (isDev) {
          // eslint-disable-next-line no-console
          console.log("[WS] ◀ message", { type: data?.event || data?.type });
        }
        try { this.opts.onEvent?.(data as BackendEvent); } catch {}
      } catch {
        // ignore
      }
    };
    this.ws = ws;
  }

  sendProcessMessage(content: string, messageId?: string, filePaths?: string[]): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ 
        command: "process_message", 
        content,
        message_id: messageId,
        file_paths: filePaths
      }));
    }
  }

  ping(): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ command: "ping" }));
    }
  }

  close(): void {
    try {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ command: "close" }));
      }
    } catch {
      // ignore
    } finally {
      try { this.ws?.close(); } catch { /* ignore */ }
      this.ws = undefined;
    }
  }
}


