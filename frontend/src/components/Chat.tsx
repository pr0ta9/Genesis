"use client";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { useApp } from "@/lib/state/AppContext";
import { createConversation, getConversation, getMessages, listConversations, sendMessage } from "@/lib/api/conversations";
import { MessageBubble } from "./MessageBubble";
import type { ConversationResponse, MessageResponse } from "@/lib/api/types";
import { buildUrl, ENDPOINTS } from "@/lib/api/config";
import { listModels, getCurrentModel } from "@/lib/api/models";
import { useRouter, usePathname } from "next/navigation";

type ChatProps = {
  // Optional URL/path to an SVG file to inline (no <img src>)
  logoPath?: string;
  // Optional pre-parsed SVG path data to render directly
  logoPaths?: string[];
  // Optional viewBox for the inline paths
  logoViewBox?: string;
  // Pixel height for the logo in the empty state
  logoSize?: number;
};

export function Chat({ logoPath, logoPaths, logoViewBox = "0 0 1024 1024", logoSize = 96 }: ChatProps) {
  const { currentConversationId, dispatch, connectSocket, wsConnected, messages, showViz } = useApp();
  const router = useRouter();
  const pathname = usePathname();
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const socketRef = useRef<ReturnType<typeof connectSocket> | null>(null);
  const lastConnectedIdRef = useRef<string | null>(null);
  const connectTimerRef = useRef<number | null>(null);
  const [inlineSvg, setInlineSvg] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setIsLoading(true);
        setConnectionError(null);
        const items = await listConversations({ limit: 50 });
        // Sort conversations by updated_at in descending order (newest first)
        const sortedItems = items.sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
        dispatch({ type: "set_conversations", conversations: sortedItems });
        // If no current conversation but we have conversations, navigate to the first one
        if (!currentConversationId && sortedItems.length > 0) {
          const firstId = sortedItems[0].id;
          // Only navigate if we're not already on a chat page
          if (typeof pathname === 'string' && !pathname.startsWith(`/chat/`)) {
            router.push(`/chat/${encodeURIComponent(firstId)}`);
          }
        } else if (!currentConversationId && sortedItems.length === 0) {
          // Create a new conversation if none exist
          const created = await createConversation("New Conversation");
          dispatch({ type: "set_conversations", conversations: [created] });
          router.push(`/chat/${encodeURIComponent(created.id)}`);
        }
      } catch (error) {
        console.error("Failed to connect to backend:", error);
        setConnectionError("Failed to connect to backend. Make sure the backend server is running on http://localhost:8000");
      } finally {
        setIsLoading(false);
      }
    })();
  }, []);

  // Fetch and inline external SVG file if a path is provided and no explicit paths were given
  useEffect(() => {
    let aborted = false;
    async function loadSvg() {
      if (!logoPath || (logoPaths && logoPaths.length > 0)) return;
      try {
        const res = await fetch(logoPath);
        if (!res.ok) return;
        const text = await res.text();
        if (aborted) return;
        // Ensure the SVG scales by height; strip width/height to let CSS control size
        const cleaned = text
          .replace(/<\?xml[^>]*>/gi, "")
          .replace(/<!DOCTYPE[^>]*>/gi, "")
          .replace(/\s(width|height)="[^"]*"/gi, "");
        setInlineSvg(cleaned);
      } catch {}
    }
    void loadSvg();
    return () => { aborted = true; };
  }, [logoPath, logoPaths]);

  useEffect(() => {
    if (!currentConversationId) {
      dispatch({ type: "set_messages", messages: [] });
      return;
    }
    
    (async () => {
      try {
        // Clear messages first when switching conversations
        dispatch({ type: "set_messages", messages: [] });
        
        const detail = await getConversation(currentConversationId);
        const msgs = detail.messages.map((m) => { 
          // For assistant messages, extract reasoning from additional_kwargs if stored reasoning doesn't exist
          let reasoning = (m as any).reasoning;
          
          if (!reasoning && m.role === 'assistant' && (m as any).additional_kwargs?.reasoning_content) {
            reasoning = {
              content: (m as any).additional_kwargs.reasoning_content,
              thinking_time: 5, // Default
              is_expanded: false,
              is_thinking: false,
              additional_kwargs: {
                reasoning_content: (m as any).additional_kwargs.reasoning_content
              }
            };
          }
          
          // Build attachments from reasoning.additional_kwargs.file_paths or legacy content hint
          let attachments: any[] | undefined = (m as any).attachments;
          const text: string = m.content || '';
          const filesStart = text.indexOf("<files>");
          const filesEnd = text.indexOf("</files>");
          const filePathsFromReasoning = (m as any)?.reasoning?.additional_kwargs?.file_paths as string[] | undefined;
          if (!attachments && Array.isArray(filePathsFromReasoning) && filePathsFromReasoning.length > 0) {
            const list = filePathsFromReasoning;
            attachments = list.map((p: string) => {
              const name = p.split(/[/\\]/).pop() || 'file';
              const ext = name.split('.').pop()?.toLowerCase() || '';
              const mime = ext === 'png' || ext === 'jpg' || ext === 'jpeg' || ext === 'gif' || ext === 'webp' ? `image/${ext === 'jpg' ? 'jpeg' : ext}`
                : ext === 'mp3' ? 'audio/mpeg'
                : ext === 'wav' ? 'audio/wav'
                : ext === 'mp4' ? 'video/mp4'
                : 'application/octet-stream';
              const url = `${buildUrl(ENDPOINTS.uploads)}/${encodeURIComponent(detail.conversation.id)}/${encodeURIComponent(name)}`;
              return { url, name, mime };
            });
          } else if (!attachments && filesStart !== -1 && filesEnd !== -1) {
            const list = text.slice(filesStart + "<files>".length, filesEnd).trim().split(/\r?\n/).filter(Boolean);
            attachments = list.map((p: string) => {
              const name = p.split(/[/\\]/).pop() || 'file';
              const ext = name.split('.').pop()?.toLowerCase() || '';
              const mime = ext === 'png' || ext === 'jpg' || ext === 'jpeg' || ext === 'gif' || ext === 'webp' ? `image/${ext === 'jpg' ? 'jpeg' : ext}`
                : ext === 'mp3' ? 'audio/mpeg'
                : ext === 'wav' ? 'audio/wav'
                : ext === 'mp4' ? 'video/mp4'
                : 'application/octet-stream';
              const url = `${buildUrl(ENDPOINTS.uploads)}/${encodeURIComponent(detail.conversation.id)}/${encodeURIComponent(name)}`;
              return { url, name, mime };
            });
          }

          // Reconstruct workflow sections for assistant messages from stored reasoning breakdown
          let workflow: { sections: Array<any> } | undefined = undefined;
          if (m.role === 'assistant') {
            const titles: Record<string, string> = {
              classify: "Classifying...",
              find_path: "Searching for possible paths...",
              route: "Selecting the path...",
              execute: "Executing...",
              finalize: "Formatting response...",
            };
            const breakdown = (reasoning as any)?.additional_kwargs?.node_breakdown as Array<any> | undefined;
            if (Array.isArray(breakdown) && breakdown.length > 0) {
              const sectionsMap = new Map<string, { node: string; title: string; status: string; reasoning_content: string; thinking_time?: number; is_thinking?: boolean; clarification?: string | null }>();
              for (const entry of breakdown) {
                const node = String(entry?.node || '').trim();
                if (!node) continue;
                const content = typeof entry?.content === 'string' ? entry.content : (entry?.content ? String(entry.content) : '');
                const time = typeof entry?.think_time_seconds === 'number' ? entry.think_time_seconds : undefined;
                const existing = sectionsMap.get(node);
                const title = titles[node] || node;
                if (existing) {
                  existing.reasoning_content = existing.reasoning_content ? `${existing.reasoning_content}\n\n${content}` : content;
                  if (typeof time === 'number') {
                    existing.thinking_time = (existing.thinking_time || 0) + time;
                  }
                } else {
                  sectionsMap.set(node, {
                    node,
                    title,
                    status: title,
                    reasoning_content: content,
                    thinking_time: time,
                    is_thinking: false,
                    clarification: null,
                  });
                }
              }
              // Attach clarifications from state if present
              const st: any = (m as any).state || {};
              if (st?.classify_clarification && sectionsMap.has('classify')) {
                const sec = sectionsMap.get('classify')!;
                sec.clarification = String(st.classify_clarification);
              }
              if (st?.route_clarification && sectionsMap.has('route')) {
                const sec = sectionsMap.get('route')!;
                sec.clarification = String(st.route_clarification);
              }
              // Ensure find_path and execute appear when inferred from state (strict conditions)
              const hasFind = sectionsMap.has('find_path');
              const hasExecute = sectionsMap.has('execute');
              const allPathsLen = Array.isArray(st?.all_paths) ? st.all_paths.length : 0;
              const chosenPathLen = Array.isArray(st?.chosen_path) ? st.chosen_path.length : 0;
              const hasResponse = typeof st?.response === 'string' && st.response.trim().length > 0;
              if (!hasFind && allPathsLen > 0) {
                sectionsMap.set('find_path', { node: 'find_path', title: titles['find_path'], status: titles['find_path'], reasoning_content: '', is_thinking: false, clarification: null });
              }
              if (!hasExecute && chosenPathLen > 0 && hasResponse) {
                sectionsMap.set('execute', { node: 'execute', title: titles['execute'], status: titles['execute'], reasoning_content: '', is_thinking: false, clarification: null });
              }
              const ordered: any[] = [];
              for (const key of ['classify', 'find_path', 'route', 'execute', 'finalize']) {
                const sec = sectionsMap.get(key);
                if (sec) ordered.push(sec);
              }
              // Include any extra nodes in insertion order
              for (const [k, sec] of sectionsMap.entries()) {
                if (!['classify', 'find_path', 'route', 'execute', 'finalize'].includes(k)) {
                  ordered.push(sec);
                }
              }
              if (ordered.length > 0) {
                workflow = { sections: ordered };
              }
            }
          }

          return { 
            id: m.id, 
            conversation_id: detail.conversation.id, 
            role: m.role, 
            content: filesStart !== -1 ? text.slice(0, filesStart).trimEnd() : text, 
            attachments,
            reasoning: reasoning,
            workflow,
            state_id: m.state?.uid as any, 
            timestamp: (m as any).timestamp ?? new Date().toISOString(), 
            has_state: Boolean(m.state),
          };
        }) as MessageResponse[];
        
        dispatch({ type: "set_messages", messages: msgs });
        // Check for any message with chosen_path or all_paths (chosen_path takes priority for display)
        console.log("🔍 Checking messages for state:", detail.messages.length, "messages");
        detail.messages.forEach((m, idx) => {
          if (m.role === 'assistant' && m.state) {
            console.log(`🔍 Message ${idx}:`, {
              hasState: !!m.state,
              state: m.state,
              stateKeys: m.state ? Object.keys(m.state) : [],
              chosen_path: (m.state as any)?.chosen_path,
              all_paths: (m.state as any)?.all_paths,
              tool_metadata: (m.state as any)?.tool_metadata
            });
          }
        });
        
        const recentWithState = [...detail.messages].reverse().find(m => 
          m.role === 'assistant' && m.state && ((m.state as any)?.chosen_path || (m.state as any)?.all_paths)
        );
        if (recentWithState) {
          console.log("🎯 Found assistant message with path data:", {
            state: recentWithState.state,
            chosen_path: (recentWithState.state as any)?.chosen_path,
            all_paths: (recentWithState.state as any)?.all_paths,
            tool_metadata: (recentWithState.state as any)?.tool_metadata
          });
          const srcState: any = recentWithState.state as any;
          const chosen = srcState?.chosen_path as Array<any> | undefined;
          const allPaths = srcState?.all_paths as Array<any> | undefined;
          const toolMeta = srcState?.tool_metadata as Array<Record<string, unknown>> | undefined;
          
          // Debug data structures
          console.log("📊 Path data structures:", {
            chosenLength: chosen?.length,
            chosenFirst: chosen?.[0],
            allPathsLength: allPaths?.length,
            allPathsFirst: allPaths?.[0],
            toolMetaLength: toolMeta?.length,
            toolMetaFirst: toolMeta?.[0]
          });
          
          // If we have paths to display
          if ((chosen && chosen.length) || (allPaths && allPaths.length)) {
            const toTokens = (p: any): string[] => {
              if (Array.isArray(p)) {
                return p.map((s: any) => {
                  if (typeof s === "string") return s;
                  // Handle PathItem objects from database
                  if (s?.name) return s.name;
                  // Handle nested path structure
                  if (Array.isArray(s)) {
                    return s.map((item: any) => item?.name || "tool").join(",");
                  }
                  return "tool";
                });
              }
              if (p && typeof p === "object") {
                const steps = p.steps || p.tool_metadata || [];
                return Array.isArray(steps) ? steps.map((s: any) => s?.name || "tool") : [];
              }
              return [];
            };
            
            // Use all_paths for graph data, but mark if we have a chosen_path
            const tokenPaths = (allPaths && allPaths.length ? allPaths : [chosen]).map(toTokens).filter(arr => arr.length > 0);
            const chosenTokenPath = chosen ? toTokens(chosen) : null;
            
            // Extract workflow types; fallback to type_savepoint for output when missing
            const inputType = srcState?.input_type as string | undefined;
            const outputType = (srcState?.output_type as string | undefined) 
              || (Array.isArray(srcState?.type_savepoint) && srcState.type_savepoint.length > 0
                    ? (srcState.type_savepoint[srcState.type_savepoint.length - 1] as string | undefined)
                    : undefined);
            
            dispatch({ type: 'hydrate_graph', allPaths: tokenPaths, toolMetadata: toolMeta || [], chosenPath: chosenTokenPath, inputType, outputType });
            
            // Calculate positions for the nodes
            const endpointTypes = ["IMAGE_IN", "IMAGE_OUT", "AUDIO_IN", "AUDIO_OUT", "VIDEO_IN", "VIDEO_OUT", "TEXT_IN", "TEXT_OUT", "FILE_IN", "FILE_OUT", "IMG"];
            const allNodes = toolMeta && toolMeta.length > 0
              ? Array.from(new Set(toolMeta.map((t: any) => t.name || "tool")))
              : Array.from(new Set(tokenPaths.flat().filter((t) => !endpointTypes.includes(t))));
            
            // Get dynamic endpoint names
            const getEndpointNames = (inputType?: string, outputType?: string) => {
              const getEndpoint = (type: string | undefined, isInput: boolean): string => {
                if (!type) return isInput ? "INPUT" : "OUTPUT";
                switch (type.toLowerCase()) {
                  case 'audiofile':
                  case 'audio':
                    return isInput ? "AUDIO_IN" : "AUDIO_OUT";
                  case 'image':
                  case 'imagefile':
                    return isInput ? "IMAGE_IN" : "IMAGE_OUT";
                  case 'video':
                  case 'videofile':
                    return isInput ? "VIDEO_IN" : "VIDEO_OUT";
                  case 'text':
                  case 'textfile':
                    return isInput ? "TEXT_IN" : "TEXT_OUT";
                  default:
                    return isInput ? "FILE_IN" : "FILE_OUT";
                }
              };
              return {
                inputEndpoint: getEndpoint(inputType, true),
                outputEndpoint: getEndpoint(outputType, false)
              };
            };
            
            const { inputEndpoint, outputEndpoint } = getEndpointNames(inputType, outputType);
            const nodesWithEndpoints = Array.from(new Set([...allNodes, inputEndpoint, outputEndpoint]));
            
            console.log("🔧 Node calculation:", {
              allNodes,
              nodesWithEndpoints,
              toolMeta: toolMeta?.map(t => ({ name: t.name, hasName: !!t.name })),
              tokenPaths
            });
            
            const { ensureColors } = await import('@/lib/graph/color');
            const { calculateNodePositions } = await import('@/lib/graph/layout');
            
            const colors = ensureColors(nodesWithEndpoints, {});
            const positions = calculateNodePositions(toolMeta || [], tokenPaths, 460, 360, {});
            
            console.log("📍 Calculated positions:", positions);
            
            console.log("[Chat] Calculated positions for nodes:", Object.keys(positions));
            
            dispatch({ type: 'set_graph_style', colors, positions });
            dispatch({ type: 'set_show_viz', show: true });
          }

          // Note: Workflow stage visibility from history is handled when building message.workflow below
        }
        // Avoid duplicate connects to the same conversation
        const isSame = lastConnectedIdRef.current === currentConversationId && socketRef.current?.ws && socketRef.current.ws.readyState === WebSocket.OPEN;
        if (!isSame) {
          // Close previous socket immediately
          try { socketRef.current?.close(); } catch {}
          socketRef.current = null;
          // Clear any pending timers
          if (connectTimerRef.current) { clearTimeout(connectTimerRef.current); connectTimerRef.current = null; }
          // Stagger reconnect slightly to allow clean close
          connectTimerRef.current = window.setTimeout(() => {
            try {
              const sock = connectSocket(currentConversationId);
              socketRef.current = sock;
              lastConnectedIdRef.current = currentConversationId;
            } catch {}
          }, 120);
        }
      } catch (error) {
        console.error("Failed to load conversation:", error);
        setConnectionError("Failed to load conversation. Please try again.");
      }
    })();
    
    return () => {
      if (connectTimerRef.current) { clearTimeout(connectTimerRef.current); connectTimerRef.current = null; }
      try { socketRef.current?.close(); } catch {}
      socketRef.current = null;
    };
  }, [currentConversationId]);

  async function onSend(filePaths?: string[]) {
    const trimmed = input.trim();
    const hasFiles = Array.isArray(filePaths) && filePaths.length > 0;
    if ((!trimmed && !hasFiles) || !currentConversationId || isLoading) {
      console.log("🚫 Send blocked:", { hasInput: !!trimmed, hasFiles, hasConversation: !!currentConversationId, isLoading });
      return;
    }
    const txt = trimmed; // May be empty if only files
    console.log("📤 Starting send process with WebSocket streaming:", { message: txt, conversationId: currentConversationId, filePaths });
    
    // Build attachment objects for immediate preview
    const attachmentObjs = (filePaths || []).map((p) => {
      const name = p.split(/[/\\]/).pop() || "file";
      const ext = name.split('.').pop()?.toLowerCase() || '';
      const mime = ext === 'png' || ext === 'jpg' || ext === 'jpeg' || ext === 'gif' || ext === 'webp' ? `image/${ext === 'jpg' ? 'jpeg' : ext}`
        : ext === 'mp3' ? 'audio/mpeg'
        : ext === 'wav' ? 'audio/wav'
        : ext === 'mp4' ? 'video/mp4'
        : 'application/octet-stream';
      let url = p;
      try {
        const convId = currentConversationId;
        const fname = name;
        // If it already looks like a URL, keep; otherwise, build preview URL with conversation + filename
        if (!/^https?:\/\//i.test(p)) {
          url = `${buildUrl(ENDPOINTS.uploads)}/${encodeURIComponent(convId)}/${encodeURIComponent(fname)}`;
        }
      } catch {}
      return { url, name, mime };
    });

    // Add the user message immediately
    const userMessage: MessageResponse = {
      id: Date.now(), // Temporary ID
      conversation_id: currentConversationId,
      role: 'user',
      content: txt,
      attachments: attachmentObjs,
      timestamp: new Date().toISOString(),
      has_state: false
    };
    
    console.log("➕ Adding user message:", userMessage);
    dispatch({ type: "append_message", message: userMessage });
    setInput("");
    
    setIsLoading(true);
    console.log("⏳ Set loading to true, preparing assistant message with reasoning");
    
    // Create assistant message placeholder that will be updated via WebSocket
    const assistantMessage: MessageResponse = {
      id: Date.now() + 1, // Temporary ID  
      conversation_id: currentConversationId,
      role: 'assistant',
      content: '', // Will be updated by streaming
      timestamp: new Date().toISOString(),
      has_state: false,
      reasoning: {
        content: '',
        thinking_time: Date.now(), // Store start time
        is_expanded: true, // Show reasoning by default
        is_thinking: true, // Start in thinking state
        additional_kwargs: { workflow_reasoning: true }
      },
      workflow: { sections: [] }
    };
    console.log("➕ Adding assistant message with reasoning placeholder");
    dispatch({ type: "append_message", message: assistantMessage });
    dispatch({ type: "start_reasoning", messageId: assistantMessage.id.toString() });
    
    try {
      // Send message via WebSocket for streaming reasoning
      if (socketRef.current?.ws && socketRef.current.ws.readyState === WebSocket.OPEN) {
        console.log("📡 Sending message via WebSocket for streaming...");
        socketRef.current.sendProcessMessage(txt, assistantMessage.id.toString(), filePaths);
        setConnectionError(null);
      } else {
        console.error("❌ WebSocket not connected (state:", socketRef.current?.ws?.readyState, "), falling back to REST API");
        // Fallback to REST API if WebSocket not available
        const res = await sendMessage(currentConversationId, txt, filePaths);
        console.log("🔄 REST API response:", res);
        
        // Update assistant message with response
        dispatch({
          type: "update_reasoning",
          messageId: assistantMessage.id.toString(),
          reasoning: "Processing your request...",
          isComplete: true
        });
        
        // Update message content directly
        dispatch({
          type: "update_message_content",
          messageId: assistantMessage.id.toString(),
          content: res.response || ''
        });
        
        // Complete reasoning
        dispatch({
          type: "complete_reasoning",
          messageId: assistantMessage.id.toString()
        });
      }
    } catch (e) {
      console.error("❌ Failed to send message:", e);
      setConnectionError("Failed to send message. Check your connection to the backend.");
      // Restore the input text if sending failed
      setInput(txt);
    } finally {
      console.log("🏁 Send process complete, setting loading to false");
      setIsLoading(false);
    }
  }

  // Enter key handling is managed inside ChatInput so it can include attachments

  return (
    <div className="h-full flex flex-col bg-white">
      {/* Connection Error */}
      {connectionError && (
        <div className="mx-6 mt-6 p-4 bg-red-50 border border-red-200 rounded-lg">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="ml-3">
              <p className="text-sm text-red-700">{connectionError}</p>
            </div>
          </div>
        </div>
      )}

      {/* Loading State - Only show when initially connecting */}
      {isLoading && messages.length === 0 && (
        <div className="h-full flex items-center justify-center">
          <div className="text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 mx-auto"></div>
            <p className="mt-2 text-sm text-gray-600">Connecting to backend...</p>
          </div>
        </div>
      )}

      {/* Chat Content - Always show if we have messages */}
      {messages.length > 0 ? (
        <>
          {/* Messages Container */}
          <div className="flex-1 overflow-hidden p-6 flex justify-center">
            <div className={`w-full ${showViz ? "max-w-2xl" : "max-w-3xl"}`}>
              <MessageList />
            </div>
          </div>

          {/* Input Section */}
          <div className="p-6 flex justify-center">
            <div className={`w-full ${showViz ? "max-w-2xl" : "max-w-3xl"}`}>
              <ChatInput 
                value={input}
                onChange={setInput}
                onSend={onSend}
                isLoading={isLoading}
              />
            </div>
          </div>
        </>
      ) : (
        /* Empty State - Centered Chat Input */
        <div className="h-full flex items-center justify-center p-6">
          <div className={`w-full ${showViz ? "max-w-2xl" : "max-w-3xl"}`}>
            {(logoPaths && logoPaths.length > 0) ? (
              <div className="w-full flex items-center justify-center mb-1">
                <svg
                  viewBox={logoViewBox}
                  className="opacity-90"
                  style={{ height: logoSize, width: "auto" }}
                  xmlns="http://www.w3.org/2000/svg"
                  aria-hidden="true"
                >
                  {logoPaths.map((d, i) => (
                    <path key={i} d={d} fill="currentColor" />
                  ))}
                </svg>
              </div>
            ) : inlineSvg ? (
              <div className="w-full flex items-center justify-center mb-1">
                <div
                  style={{ height: logoSize, width: "auto" }}
                  className="opacity-90 [&>svg]:h-full [&>svg]:w-auto"
                  // Inline the SVG markup (no <img src>)
                  dangerouslySetInnerHTML={{ __html: inlineSvg }}
                />
              </div>
            ) : null}
            <div className="mt-5">
              <ChatInput 
                value={input}
                onChange={setInput}
                onSend={onSend}
                isLoading={isLoading}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend: (filePaths?: string[]) => void;
  isLoading?: boolean;
}

function ChatInput({ value, onChange, onSend, isLoading = false }: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const attachmentScrollRef = useRef<HTMLDivElement>(null);
  const attachmentTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const hasText = value.trim().length > 0;
  const { dispatch, showViz, showExecution, currentConversationId } = useApp();

  type AttachmentLocal = {
    id: string;
    file: File;
    url: string; // object URL for preview
    mime: string;
    name: string;
    size: number;
  };

  const [attachments, setAttachments] = useState<AttachmentLocal[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [models, setModels] = useState<Array<{ id: string; name: string; provider: string }>>([]);
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [isModelOpen, setIsModelOpen] = useState(false);

  useEffect(() => {
    const element = attachmentScrollRef.current;
    if (!element) return;

    const handleScroll = () => {
      element.classList.add('scrolling');
      
      if (attachmentTimeoutRef.current) {
        clearTimeout(attachmentTimeoutRef.current);
      }
      
      attachmentTimeoutRef.current = setTimeout(() => {
        element.classList.remove('scrolling');
      }, 2000);
    };

    element.addEventListener('scroll', handleScroll, { passive: true });

    return () => {
      element.removeEventListener('scroll', handleScroll);
      if (attachmentTimeoutRef.current) {
        clearTimeout(attachmentTimeoutRef.current);
      }
    };
  }, []);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const [list, current] = await Promise.allSettled([
          listModels(),
          getCurrentModel(),
        ]);
        if (!mounted) return;
        if (list.status === "fulfilled") {
          setModels(list.value || []);
        }
        if (current.status === "fulfilled") {
          setSelectedModel(current.value?.current || "");
        } else if (list.status === "fulfilled" && list.value.length > 0) {
          setSelectedModel(list.value[0].id);
        }
      } catch {
        // silently ignore
      }
    })();
    return () => { mounted = false; };
  }, []);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = textareaRef.current.scrollHeight + 'px';
    }
  }, [value]);

  // Cleanup object URLs
  useEffect(() => {
    return () => {
      attachments.forEach(a => URL.revokeObjectURL(a.url));
    };
  }, [attachments]);

  function handleAttachClick() {
    fileInputRef.current?.click();
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    const newItems: AttachmentLocal[] = Array.from(files).map((f) => ({
      id: `${f.name}-${f.size}-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      file: f,
      url: URL.createObjectURL(f),
      mime: f.type || 'application/octet-stream',
      name: f.name,
      size: f.size,
    }));
    setAttachments((prev) => [...prev, ...newItems].slice(0, 10));
    // Reset input to allow re-uploading same file name
    e.target.value = '';
  }

  function addFiles(list: FileList | File[]) {
    const files = Array.from(list);
    if (files.length === 0) return;
    const newItems: AttachmentLocal[] = files.map((f) => ({
      id: `${f.name}-${f.size}-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      file: f,
      url: URL.createObjectURL(f),
      mime: f.type || 'application/octet-stream',
      name: f.name,
      size: f.size,
    }));
    setAttachments((prev) => [...prev, ...newItems].slice(0, 10));
  }

  function removeAttachment(id: string) {
    setAttachments((prev) => {
      const next = prev.filter((a) => a.id !== id);
      const removed = prev.find((a) => a.id === id);
      if (removed) URL.revokeObjectURL(removed.url);
      return next;
    });
  }

  function handlePaste(e: React.ClipboardEvent<HTMLTextAreaElement | HTMLDivElement>) {
    const items = e.clipboardData?.items;
    if (!items) return;
    const files: File[] = [];
    for (let i = 0; i < items.length; i++) {
      const it = items[i];
      if (it.kind === 'file') {
        const f = it.getAsFile();
        if (f) files.push(f);
      }
    }
    if (files.length > 0) {
      addFiles(files);
      // Do not prevent default for text; allow text paste as well
    }
  }

  function handleDragOver(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
  }
  function handleDragEnter(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }
  function handleDragLeave(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }
  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    const dt = e.dataTransfer;
    if (!dt) return;
    if (dt.files && dt.files.length > 0) {
      addFiles(dt.files);
    }
  }

  function isImage(mime: string) {
    return mime.startsWith('image/');
  }

  async function handleSend() {
    await onSendWithAttachments();
  }

  async function uploadAttachments(): Promise<string[]> {
    if (attachments.length === 0) return [];
    const form = new FormData();
    for (const a of attachments) {
      form.append("files", a.file, a.name);
    }
    try {
      const url = currentConversationId 
        ? `${buildUrl(ENDPOINTS.uploads)}?conversation_id=${encodeURIComponent(currentConversationId)}`
        : buildUrl(ENDPOINTS.uploads);
      const res = await fetch(url, {
        method: 'POST',
        body: form,
      });
      if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
      const data = await res.json();
      const paths = Array.isArray(data?.file_paths) ? data.file_paths as string[] : [];
      return paths;
    } catch (e) {
      console.error("Attachment upload failed", e);
      return [];
    }
  }

  async function onSendWithAttachments() {
    const filePaths = await uploadAttachments();
    try {
      await onSend(filePaths);
    } finally {
      setAttachments((prev) => {
        prev.forEach((a) => URL.revokeObjectURL(a.url));
        return [];
      });
    }
  }

  return (
    <div 
      className="flex flex-col gap-3.5 p-4 bg-gray-50 rounded-3xl"
      onDragOver={handleDragOver}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onPaste={handlePaste}
    >
      {/* Header: Attachments Preview Row */}
      {attachments.length > 0 && (
        <div className="-mx-2.5 -mt-2.5 mb-0.5 flex flex-col">
          <div className="w-full">
            <div 
              ref={attachmentScrollRef}
              className="horizontal-scroll-fade-mask flex flex-nowrap gap-2 overflow-x-auto px-2.5 pt-2.5 pb-1.5 scrollbar-smart [--edge-fade-distance:1rem]"
            >
              {attachments.map((att) => (
                <div key={att.id} className="group relative inline-block text-sm">
                  <div className="relative overflow-hidden border rounded-2xl border-gray-200 bg-white">
                    <div className="h-36 w-36 flex items-center justify-center bg-gray-100 text-gray-600">
                      {isImage(att.mime) ? (
                        <span
                          className="h-full w-full bg-cover bg-center"
                          style={{ backgroundImage: `url('${att.url}')` }}
                        />
                      ) : (
                        <div className="flex flex-col items-center justify-center p-4 text-xs text-center">
                          <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor" className="mb-1 text-gray-500"><path d="M4 2.5A1.5 1.5 0 015.5 1h5.879a1.5 1.5 0 011.06.44l3.121 3.12c.28.28.44.66.44 1.06V15.5A1.5 1.5 0 0114.5 17h-9A1.5 1.5 0 014 15.5v-13zM11 2.5V5a1 1 0 001 1h2.5"/></svg>
                          <div className="truncate max-w-[8rem]">{att.name}</div>
                        </div>
                      )}
                    </div>
                    <div className="absolute end-1.5 top-1.5 inline-flex gap-1">
                      <button
                        aria-label="Remove file"
                        onClick={() => removeAttachment(att.id)}
                        className="transition-colors flex h-6 w-6 items-center justify-center rounded-full border border-black/10 bg-black text-white dark:border-white/10 dark:bg-white dark:text-black"
                        type="button"
                      >
                        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" className="icon-sm"><path d="M11.1152 3.91503C11.3868 3.73594 11.756 3.7658 11.9951 4.00488C12.2341 4.24395 12.264 4.61309 12.0849 4.88476L11.9951 4.99511L8.99018 7.99999L11.9951 11.0049L12.0849 11.1152C12.264 11.3869 12.2341 11.756 11.9951 11.9951C11.756 12.2342 11.3868 12.2641 11.1152 12.085L11.0048 11.9951L7.99995 8.99023L4.99506 11.9951C4.7217 12.2685 4.2782 12.2685 4.00483 11.9951C3.73146 11.7217 3.73146 11.2782 4.00483 11.0049L7.00971 7.99999L4.00483 4.99511L3.91499 4.88476C3.73589 4.61309 3.76575 4.24395 4.00483 4.00488C4.24391 3.7658 4.61305 3.73594 4.88471 3.91503L4.99506 4.00488L7.99995 7.00976L11.0048 4.00488L11.1152 3.91503Z"/></svg>
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
      {/* Text Input Container */}
      <div className="relative">
        <div className="max-h-96 w-full overflow-y-auto break-words transition-opacity duration-200 min-h-[1.5rem]">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void handleSend(); } }}
            placeholder="Ask anything"
            className="w-full p-0 border-0 resize-none bg-transparent text-gray-900 placeholder-gray-400 focus:outline-none min-h-[1.5rem] overflow-hidden text-base leading-6"
            rows={1}
          />
        </div>
      </div>

      {/* Bottom Controls */}
      <div className="flex gap-2.5 w-full items-center">
        {/* Left Side - File Upload Button */}
        <div className="relative shrink-0">
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            multiple
            onChange={handleFileChange}
            accept="image/*,application/pdf,.txt,.md,.json,.csv"
          />
          <button
            onClick={handleAttachClick}
            className="inline-flex items-center justify-center relative shrink-0 transition-all h-8 w-8 rounded-full bg-gray-50 text-gray-600 hover:text-gray-800 hover:bg-gray-200 active:scale-95"
            type="button"
            aria-label="Attach file"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
            </svg>
          </button>
        </div>

        {/* Spacer */}
        <div className="flex-1"></div>

        {/* Right Side Controls */}
        <div className="flex items-center gap-2 relative">
          {/* Toggle Viz Button */}
          <button
            onClick={() => dispatch({ type: "toggle_show_viz" })}
            className={`inline-flex items-center justify-center relative shrink-0 h-7 px-2 rounded-md text-xs border ${showViz ? "bg-gray-900 text-white border-gray-900" : "bg-gray-50 text-gray-700 border-gray-200 hover:bg-gray-100"}`}
            type="button"
            aria-label="Toggle visualization"
            title="Toggle visualization"
          >
            {showViz ? "Hide Panel" : "Show Panel"}
          </button>
          
          {/* Toggle Execution Button - Only show if visualization is enabled */}
          {showViz && (
            <button
              onClick={() => dispatch({ type: "toggle_show_execution" })}
              className={`inline-flex items-center justify-center relative shrink-0 h-7 px-2 rounded-md text-xs border ${showExecution ? "bg-orange-600 text-white border-orange-600" : "bg-orange-50 text-orange-700 border-orange-200 hover:bg-orange-100"}`}
              type="button"
              aria-label="Toggle execution view"
              title="Toggle execution view"
            >
              {showExecution ? "Hide Execution" : "Show Execution"}
            </button>
          )}
          {/* Model Selector (drop-up) */}
          <div className="overflow-visible shrink-0">
            <div className="relative">
              <button
                onClick={() => setIsModelOpen((o) => !o)}
                className="inline-flex items-center justify-center relative shrink-0 h-7 border border-transparent text-gray-700 ml-1.5 inline-flex items-start gap-1 rounded-md text-sm opacity-80 transition hover:opacity-100 hover:bg-gray-100 hover:border-gray-400 px-1.5"
                type="button"
                aria-haspopup="listbox"
                aria-expanded={isModelOpen}
              >
                <div className="inline-flex gap-1 text-sm h-3.5 leading-none items-baseline">
                  <div className="flex items-center gap-1">
                    <div className="whitespace-nowrap tracking-tight select-none text-xs">
                      {selectedModel || (models[0]?.id ?? "Model")}
                    </div>
                  </div>
                </div>
                <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" fill="currentColor" viewBox="0 0 256 256" className="text-gray-500 shrink-0">
                  <path d="M213.66,101.66l-80,80a8,8,0,0,1-11.32,0l-80-80A8,8,0,0,1,53.66,90.34L128,164.69l74.34-74.35a8,8,0,0,1,11.32,11.32Z"></path>
                </svg>
              </button>
              {isModelOpen && (
                <div className="absolute bottom-full right-0 mb-2 z-10 min-w-[12rem] max-h-56 overflow-auto rounded-xl border border-gray-200 bg-white shadow-xl">
                  <ul role="listbox" className="py-1">
                    {models.length === 0 ? (
                      <li className="px-3 py-2 text-xs text-gray-500">No models</li>
                    ) : (
                      models.map((m) => (
                        <li key={m.id}>
                          <button
                            type="button"
                            role="option"
                            aria-selected={selectedModel === m.id}
                            onClick={() => { setSelectedModel(m.id); setIsModelOpen(false); }}
                            className={`w-full text-left px-3 py-2 text-sm hover:bg-gray-100 ${selectedModel === m.id ? 'bg-gray-50' : ''}`}
                          >
                            <div className="flex items-center justify-between">
                              <span className="truncate">
                                {m.id}
                              </span>
                              <span className="ml-2 text-[10px] text-gray-500 uppercase">{m.provider}</span>
                            </div>
                          </button>
                        </li>
                      ))
                    )}
                  </ul>
                </div>
              )}
            </div>
          </div>

          {/* Send Button */}
          <div>
            <button 
              onClick={handleSend}
              disabled={!(hasText || attachments.length > 0)}
              className={`inline-flex items-center justify-center relative shrink-0 h-8 w-8 rounded-full active:scale-95 transition-all duration-200 ${
                (hasText || attachments.length > 0)
                  ? 'bg-black text-white hover:bg-gray-800' 
                  : 'bg-gray-200 text-gray-400 opacity-50 cursor-not-allowed'
              }`}
              type="button" 
              aria-label="Send message"
            >
              {isLoading && (hasText || attachments.length > 0) ? (
                <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div>
              ) : (
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 256 256">
                  <path d="M208.49,120.49a12,12,0,0,1-17,0L140,69V216a12,12,0,0,1-24,0V69L64.49,120.49a12,12,0,0,1-17-17l72-72a12,12,0,0,1,17,0l72,72A12,12,0,0,1,208.49,120.49Z"></path>
                </svg>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function MessageList() {
  const { messages } = useApp();
  const endRef = useRef<HTMLDivElement | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  // Smart scrollbar functionality
  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;

    const handleScroll = () => {
      // Add scrolling class when scrolling starts
      element.classList.add('scrolling');
      
      // Clear existing timeout
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
      
      // Set timeout to remove scrolling class after 2 seconds
      timeoutRef.current = setTimeout(() => {
        element.classList.remove('scrolling');
      }, 2000);
    };

    element.addEventListener('scroll', handleScroll, { passive: true });

    return () => {
      element.removeEventListener('scroll', handleScroll);
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);
  
  return (
    <div 
      ref={scrollRef}
      className="h-full overflow-y-auto space-y-6 scrollbar-smart"
    >
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} />
      ))}
      <div ref={endRef} />
    </div>
  );
}


