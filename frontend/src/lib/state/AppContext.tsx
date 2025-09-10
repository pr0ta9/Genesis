"use client";
import React, { createContext, useContext, useMemo, useReducer } from "react";
import type { ConversationResponse, MessageResponse, StateResponse } from "../api/types";
import { ConversationSocket, type BackendEvent } from "../ws/client";
import { getState } from "../api/states";
import { updateConversation } from "../api/conversations";
import { ensureColors } from "../graph/color";
import { calculateNodePositions } from "../graph/layout";

export type Stage =
  | "start"
  | "classify"
  | "find_path"
  | "route"
  | "execute"
  | "finalize"
  | "waiting_for_feedback";

interface AppState {
  conversations: ConversationResponse[];
  currentConversationId?: string;
  messages: MessageResponse[];
  stage: Stage;
  latestState?: StateResponse;
  reasoningLog: Array<{ timestamp: string; text: string; node?: string }>;
  wsConnected: boolean;
  currentReasoningMessageId?: string; // Track which message is currently reasoning
  showViz: boolean;
  showExecution: boolean; // Toggle for execution panel visibility
  splitRatio: number; // proportion of width for the right panel (Propagation), 0..1
  verticalSplitRatio: number; // proportion of height for the propagation panel vs execution panel, 0..1
  // Graph data cache (frontend-managed)
  graph: {
    allPaths: string[][]; // tokens with endpoints normalized
    currentPaths?: string[][]; // UI-ephemeral: what Propagation/Pipeline actually render
    chosenPath?: string[] | null; // the selected path if any
    toolMetadata: Array<Record<string, unknown>>;
    colors: Record<string, string>;
    positions: Record<string, { x: number; y: number }>;
    population?: { startedAt: number; speed: number };
    reduceAnimationCompleted?: boolean; // tracks when path reduction animation finishes
    inputType?: string; // workflow input type (e.g., 'audiofile', 'image')
    outputType?: string; // workflow output type
    animation?: {
      mode: 'find_path' | 'reduce' | 'chosen_path' | null;
      populate: { currentIndex: number; completed: boolean };
      reduce: { started: boolean; currentIndex: number };
    };
  };
  // Execution UI data
  console: Array<{ timestamp: string; type: 'stdout' | 'stderr'; line: string; step_index?: number; tool_name?: string }>;
  currentToolName?: string;
  currentStepIndex?: number;
  lastSavedFile?: { path: string; mime?: string; tool_name?: string; step_index?: number };
  // Track the latest saved file per step for accurate step previews
  lastFileByStep?: Record<number, { path: string; mime?: string; tool_name?: string; step_index?: number }>;
}

type Action =
  | { type: "set_conversations"; conversations: ConversationResponse[] }
  | { type: "upsert_conversation"; conversation: ConversationResponse }
  | { type: "set_current_conversation"; id: string }
  | { type: "set_messages"; messages: MessageResponse[] }
  | { type: "append_message"; message: MessageResponse }
  | { type: "set_stage"; stage: Stage }
  | { type: "set_state"; state: StateResponse }
  | { type: "append_reasoning"; entry: { timestamp: string; text: string; node?: string } }
  | { type: "ws_status"; connected: boolean }
  | { type: "start_reasoning"; messageId: string }
  | { type: "update_reasoning"; messageId: string; reasoning: string; isComplete?: boolean }
  | { type: "complete_reasoning"; messageId: string; thinkingTime?: number }
  | { type: "update_message_content"; messageId: string; content: string }
  // Workflow reasoning per-stage
  | { type: "workflow_start_stage"; messageId: string; node: string; title: string; status: string; startedAt?: string }
  | { type: "workflow_update_reasoning"; messageId: string; node: string; text: string }
  | { type: "workflow_clarification"; messageId: string; node: string; text: string }
  | { type: "workflow_complete_stage"; messageId: string; node: string; thinkingTime?: number; status?: string; completedAt?: string }
  | { type: "handle_completion"; response: string; reasoning?: any; messageId?: string }
  | { type: "set_show_viz"; show: boolean }
  | { type: "toggle_show_viz" }
  | { type: "set_show_execution"; show: boolean }
  | { type: "toggle_show_execution" }
  | { type: "set_split_ratio"; ratio: number }
  | { type: "set_vertical_split_ratio"; ratio: number }
  | { type: "hydrate_graph"; allPaths: string[][]; toolMetadata?: Array<Record<string, unknown>>; chosenPath?: string[] | null; inputType?: string; outputType?: string }
  | { type: "set_graph_style"; colors: Record<string, string>; positions: Record<string, { x: number; y: number }> }
  | { type: "start_population"; startedAt?: number; speed?: number }
  | { type: "set_reduce_animation_completed"; completed: boolean }
  | { type: "clear_graph" }
  // Graph animation sync (shared between Propagation and Pipeline)
  | { type: "set_animation_mode"; mode: 'find_path' | 'reduce' | 'chosen_path' | null }
  | { type: "set_populate_index"; index: number }
  | { type: "set_populate_completed"; completed: boolean }
  | { type: "set_reduce_started"; started: boolean }
  | { type: "set_reduce_index"; index: number }
  // UI-ephemeral graph rendering/animation helpers
  | { type: "ui/reset_for_find_path" }
  | { type: "ui/init_current_paths_from_endpoints"; endpoints: string[] }
  | { type: "ui/append_current_path"; path: string[] }
  | { type: "ui/remove_current_path"; pathId: string }
  | { type: "ui/show_chosen_only" }
  | { type: "ui/open_panel"; id: string }
  // Update only the chosen path without resetting animations/paths
  | { type: "set_chosen_path"; chosenPath: string[] | null }
  // Execution streaming events
  | { type: "append_console_line"; entry: { timestamp: string; type: 'stdout' | 'stderr'; line: string; step_index?: number; tool_name?: string } }
  | { type: "file_saved"; file: { path: string; mime?: string; tool_name?: string; step_index?: number } }
  | { type: "execution_step_complete"; tool_name: string; step_index: number }
  | { type: "select_execution_step"; tool_name: string; step_index: number }
  // Track current executing tool and step during streaming
  | { type: "set_current_execution"; tool_name?: string; step_index?: number };

function reducer(state: AppState, action: Action): AppState {
  console.log("🔄 State action:", action.type, action);
  
  switch (action.type) {
    case "set_conversations":
      console.log("📋 Setting conversations:", action.conversations.length, "items");
      return { ...state, conversations: action.conversations };
    case "upsert_conversation": {
      const existing = state.conversations.find(c => c.id === action.conversation.id);
      const updated = existing
        ? state.conversations.map(c => c.id === action.conversation.id ? action.conversation : c)
        : [action.conversation, ...state.conversations];
      return { ...state, conversations: updated };
    }
    case "set_current_conversation":
      if (state.currentConversationId === action.id) {
        return state;
      }
      console.log("🎯 Setting current conversation:", action.id);
      return { ...state, currentConversationId: action.id };
    case "set_messages":
      console.log("💬 Setting messages:", action.messages.length, "messages");
      return { ...state, messages: action.messages };
    case "append_message":
      console.log("➕ Appending message:", action.message.role, "-", action.message.content?.slice(0, 50));
      const newState = { ...state, messages: [...state.messages, action.message] };
      console.log("📊 New message count:", newState.messages.length);
      return newState;
    case "set_stage":
      return { ...state, stage: action.stage };
    case "set_state":
      return { ...state, latestState: action.state };
    case "append_reasoning":
      return { ...state, reasoningLog: [...state.reasoningLog, action.entry] };
    case "ws_status":
      return { ...state, wsConnected: action.connected };
    case "start_reasoning":
      return { 
        ...state, 
        currentReasoningMessageId: action.messageId,
        messages: state.messages.map(m => 
          m.id.toString() === action.messageId 
            ? { 
                ...m, 
                reasoning: { 
                  content: "", 
                  thinking_time: Date.now(), // Store start time
                  is_expanded: false, 
                  is_thinking: true 
                } 
              }
            : m
        )
      };
    case "update_reasoning":
      return {
        ...state,
        messages: state.messages.map(m => 
          m.id.toString() === action.messageId && m.reasoning
            ? { 
                ...m, 
                reasoning: { 
                  ...m.reasoning,
                  content: action.reasoning,
                  is_thinking: !action.isComplete
                } 
              }
            : m
        )
      };
    case "complete_reasoning":
      return {
        ...state,
        currentReasoningMessageId: undefined,
        messages: state.messages.map(m => 
          m.id.toString() === action.messageId && m.reasoning
            ? { 
                ...m, 
                reasoning: { 
                  ...m.reasoning,
                  thinking_time: action.thinkingTime || Math.floor((Date.now() - (m.reasoning.thinking_time || Date.now())) / 1000),
                  is_thinking: false
                } 
              }
            : m
        )
      };
    case "update_message_content":
      console.log("📝 Updating message content:", action.messageId, action.content?.slice(0, 50));
      return {
        ...state,
        messages: state.messages.map(m => 
          m.id.toString() === action.messageId
            ? { ...m, content: action.content }
            : m
        )
      };
    case "workflow_start_stage": {
      const now = new Date().toISOString();
      return {
        ...state,
        messages: state.messages.map(m =>
          m.id.toString() === action.messageId
            ? {
                ...m,
                workflow: {
                  sections: (() => {
                    const existing = (m.workflow?.sections) || [];
                    // If a section for this node already exists, do not add another
                    if (existing.some(s => s.node === action.node)) return existing;
                    return [
                      ...existing,
                      {
                        node: action.node,
                        title: action.title,
                        status: action.status,
                        started_at: action.startedAt || now,
                        is_thinking: true,
                        reasoning_content: "",
                        clarification: null,
                      },
                    ];
                  })(),
                },
              }
            : m
        ),
      };
    }
    case "workflow_update_reasoning": {
      return {
        ...state,
        messages: state.messages.map(m =>
          m.id.toString() === action.messageId
            ? {
                ...m,
                workflow: {
                  sections: (m.workflow?.sections || []).map(s =>
                    s.node === action.node
                      ? { ...s, reasoning_content: ((s.reasoning_content || "") + (action.text || "")).slice(-50000) }
                      : s
                  ),
                },
              }
            : m
        ),
      };
    }
    case "workflow_clarification": {
      return {
        ...state,
        messages: state.messages.map(m =>
          m.id.toString() === action.messageId
            ? {
                ...m,
                workflow: {
                  sections: (m.workflow?.sections || []).map(s =>
                    s.node === action.node
                      ? { ...s, clarification: (s.clarification ? s.clarification + "\n\n" : "") + action.text }
                      : s
                  ),
                },
              }
            : m
        ),
      };
    }
    case "workflow_complete_stage": {
      const now = new Date().toISOString();
      return {
        ...state,
        messages: state.messages.map(m =>
          m.id.toString() === action.messageId
            ? {
                ...m,
                workflow: {
                  sections: (m.workflow?.sections || []).map(s =>
                    s.node === action.node
                      ? {
                          ...s,
                          is_thinking: false,
                          completed_at: action.completedAt || now,
                          thinking_time: (() => {
                            if (typeof action.thinkingTime === 'number') return action.thinkingTime;
                            const start = s.started_at ? Date.parse(s.started_at) : undefined;
                            const end = action.completedAt ? Date.parse(action.completedAt) : Date.now();
                            if (start && end && end > start) {
                              return (end - start) / 1000;
                            }
                            return s.thinking_time;
                          })(),
                          status: action.status || s.status,
                        }
                      : s
                  ),
                },
              }
            : m
        ),
      };
    }
    case "set_show_viz":
      return { ...state, showViz: action.show };
    case "toggle_show_viz":
      return { ...state, showViz: !state.showViz };
    case "set_show_execution":
      return { ...state, showExecution: action.show };
    case "toggle_show_execution":
      return { ...state, showExecution: !state.showExecution };
    case "set_split_ratio":
      return { ...state, splitRatio: Math.max(0, Math.min(1, action.ratio)) };
    case "set_vertical_split_ratio":
      return { ...state, verticalSplitRatio: Math.max(0.25, Math.min(0.75, action.ratio)) };
    case "hydrate_graph": {
      // Get dynamic endpoint names based on workflow types
      const { inputEndpoint, outputEndpoint } = getEndpointNames(action.inputType, action.outputType);
      
      // Normalize tokens: add endpoints if missing
      const norm = (p: string[]): string[] => {
        const first = p[0];
        const last = p[p.length - 1];
        
        // Check if first token is already an endpoint (any type)
        const isStartEndpoint = first === "IMG" || first === "IMAGE_IN" || first === "AUDIO_IN" || first === "VIDEO_IN" || first === "TEXT_IN" || first === "FILE_IN";
        const isEndEndpoint = last === "IMG" || last === "IMAGE_OUT" || last === "AUDIO_OUT" || last === "VIDEO_OUT" || last === "TEXT_OUT" || last === "FILE_OUT";
        
        const start = isStartEndpoint ? first : inputEndpoint;
        const end = isEndEndpoint ? last : outputEndpoint;
        
        // Filter out all known endpoint types from middle
        const endpointTypes = ["IMAGE_IN", "IMAGE_OUT", "AUDIO_IN", "AUDIO_OUT", "VIDEO_IN", "VIDEO_OUT", "TEXT_IN", "TEXT_OUT", "FILE_IN", "FILE_OUT", "IMG"];
        const mids = p.filter((t) => !endpointTypes.includes(t));
        
        return [start, ...mids, end];
      };
      
      const allPaths = action.allPaths.map(norm);
      const chosenPath = action.chosenPath ? norm(action.chosenPath) : null;
      
      return { 
        ...state, 
        graph: { 
          ...state.graph, 
          allPaths, 
          currentPaths: state.graph.currentPaths && state.graph.currentPaths.length > 0 ? state.graph.currentPaths : [],
          chosenPath,
          toolMetadata: action.toolMetadata || state.graph.toolMetadata,
          inputType: action.inputType || state.graph.inputType,
          outputType: action.outputType || state.graph.outputType,
          reduceAnimationCompleted: false, // Reset animation state for new graph
          // Reset shared animation state on new hydrate
          animation: {
            mode: null,
            populate: { currentIndex: 0, completed: false },
            reduce: { started: false, currentIndex: 0 }
          }
        } 
      };
    }
    case "set_graph_style":
      return { ...state, graph: { ...state.graph, colors: action.colors, positions: action.positions } };
    case "start_population": {
      const startedAt = action.startedAt ?? Date.now();
      const speed = action.speed ?? state.graph.population?.speed ?? 1;
      return { 
        ...state, 
        graph: { 
          ...state.graph, 
          population: { startedAt, speed },
          animation: {
            mode: 'find_path',
            populate: { currentIndex: 0, completed: false },
            reduce: { started: false, currentIndex: 0 }
          }
        } 
      };
    }
    case "set_reduce_animation_completed":
      return { ...state, graph: { ...state.graph, reduceAnimationCompleted: action.completed } };
    case "set_animation_mode": {
      const prev = state.graph.animation || { mode: null, populate: { currentIndex: 0, completed: false }, reduce: { started: false, currentIndex: 0 } };
      return { ...state, graph: { ...state.graph, animation: { ...prev, mode: action.mode } } };
    }
    case "set_populate_index": {
      const prev = state.graph.animation || { mode: null, populate: { currentIndex: 0, completed: false }, reduce: { started: false, currentIndex: 0 } };
      return { ...state, graph: { ...state.graph, animation: { ...prev, populate: { ...prev.populate, currentIndex: Math.max(0, action.index) } } } };
    }
    case "set_populate_completed": {
      const prev = state.graph.animation || { mode: null, populate: { currentIndex: 0, completed: false }, reduce: { started: false, currentIndex: 0 } };
      return { ...state, graph: { ...state.graph, animation: { ...prev, populate: { ...prev.populate, completed: action.completed } } } };
    }
    case "set_reduce_started": {
      const prev = state.graph.animation || { mode: null, populate: { currentIndex: 0, completed: false }, reduce: { started: false, currentIndex: 0 } };
      return { ...state, graph: { ...state.graph, animation: { ...prev, reduce: { ...prev.reduce, started: action.started } } } };
    }
    case "set_reduce_index": {
      const prev = state.graph.animation || { mode: null, populate: { currentIndex: 0, completed: false }, reduce: { started: false, currentIndex: 0 } };
      return { ...state, graph: { ...state.graph, animation: { ...prev, reduce: { ...prev.reduce, currentIndex: Math.max(0, action.index) } } } };
    }
    // UI-ephemeral helpers for Propagation/Pipeline
    case "ui/reset_for_find_path": {
      const prevAnim = state.graph.animation || { mode: null, populate: { currentIndex: 0, completed: false }, reduce: { started: false, currentIndex: 0 } };
      return {
        ...state,
        graph: {
          ...state.graph,
          currentPaths: [],
          animation: { ...prevAnim, mode: 'find_path', populate: { ...prevAnim.populate, currentIndex: 0, completed: false }, reduce: { ...prevAnim.reduce, started: false, currentIndex: 0 } },
        },
      };
    }
    case "ui/init_current_paths_from_endpoints": {
      const eps = action.endpoints || [];
      const stub = eps.length >= 2 ? [eps[0], eps[eps.length - 1]] : [];
      const prevAnim = state.graph.animation || { mode: null, populate: { currentIndex: 0, completed: false }, reduce: { started: false, currentIndex: 0 } };
      return {
        ...state,
        graph: {
          ...state.graph,
          currentPaths: stub.length ? [stub] : [],
          animation: { ...prevAnim, mode: 'find_path', populate: { ...prevAnim.populate, currentIndex: 0, completed: false } },
        },
      };
    }
    case "ui/append_current_path": {
      const existing = state.graph.currentPaths || [];
      const id = JSON.stringify(action.path);
      const seen = new Set(existing.map(p => JSON.stringify(p)));
      if (seen.has(id)) return state;
      return { ...state, graph: { ...state.graph, currentPaths: [...existing, action.path] } };
    }
    case "ui/remove_current_path": {
      const existing = state.graph.currentPaths || [];
      return { ...state, graph: { ...state.graph, currentPaths: existing.filter(p => JSON.stringify(p) !== action.pathId) } };
    }
    case "ui/show_chosen_only": {
      const cp = state.graph.chosenPath && state.graph.chosenPath.length ? [state.graph.chosenPath] : [];
      const prevAnim = state.graph.animation || { mode: null, populate: { currentIndex: 0, completed: false }, reduce: { started: false, currentIndex: 0 } };
      return { ...state, graph: { ...state.graph, currentPaths: cp, animation: { ...prevAnim, mode: 'chosen_path', reduce: { ...prevAnim.reduce, started: false } } } };
    }
    case "ui/open_panel": {
      // Minimal: open propagation panel by ensuring showViz is true
      return { ...state, showViz: true };
    }
    case "set_chosen_path": {
      // Normalize chosen path with dynamic endpoints using current graph workflow types
      const { inputEndpoint, outputEndpoint } = getEndpointNames(state.graph.inputType, state.graph.outputType);
      const p = action.chosenPath || [];
      const first = p[0];
      const last = p[p.length - 1];
      const isStartEndpoint = first === "IMG" || first === "IMAGE_IN" || first === "AUDIO_IN" || first === "VIDEO_IN" || first === "TEXT_IN" || first === "FILE_IN";
      const isEndEndpoint = last === "IMG" || last === "IMAGE_OUT" || last === "AUDIO_OUT" || last === "VIDEO_OUT" || last === "TEXT_OUT" || last === "FILE_OUT";
      const start = isStartEndpoint ? first : inputEndpoint;
      const end = isEndEndpoint ? last : outputEndpoint;
      const endpointTypes = ["IMAGE_IN", "IMAGE_OUT", "AUDIO_IN", "AUDIO_OUT", "VIDEO_IN", "VIDEO_OUT", "TEXT_IN", "TEXT_OUT", "FILE_IN", "FILE_OUT", "IMG"];
      const mids = p.filter((t) => !endpointTypes.includes(t));
      const normalized = action.chosenPath ? [start, ...mids, end] : null;
      return { ...state, graph: { ...state.graph, chosenPath: normalized } };
    }
    case "clear_graph":
      return { ...state, graph: { allPaths: [], toolMetadata: [], colors: {}, positions: {} } };
    case "append_console_line":
      return { ...state, console: [...state.console, action.entry].slice(-10000) };
    case "file_saved":
      return { 
        ...state, 
        lastSavedFile: action.file,
        lastFileByStep: (() => {
          const map = { ...(state.lastFileByStep || {}) } as Record<number, { path: string; mime?: string; tool_name?: string; step_index?: number }>;
          const idx = typeof action.file?.step_index === 'number' ? action.file.step_index : undefined;
          if (typeof idx === 'number') {
            map[idx] = action.file;
          }
          return map;
        })()
      };
    case "execution_step_complete":
      return { ...state, currentToolName: action.tool_name, currentStepIndex: action.step_index };
    case "select_execution_step":
      return { ...state, currentToolName: action.tool_name, currentStepIndex: action.step_index, showExecution: true };
    case "set_current_execution":
      return { ...state, currentToolName: action.tool_name, currentStepIndex: action.step_index };
    case "handle_completion":
      console.log("🔧 Reducer handling completion with:", { 
        providedMessageId: action.messageId,
        currentReasoningMessageId: state.currentReasoningMessageId,
        messagesCount: state.messages.length
      });
      
      // Use provided message ID first, then fallback to current reasoning message ID
      let targetMessageId = action.messageId || state.currentReasoningMessageId;
      
      // Final fallback: find the most recent assistant message
      if (!targetMessageId && state.messages.length > 0) {
        const lastAssistantMessage = [...state.messages].reverse().find(m => m.role === 'assistant');
        if (lastAssistantMessage) {
          targetMessageId = lastAssistantMessage.id.toString();
          console.log("🎯 Reducer using last assistant message as fallback:", targetMessageId);
        }
      }
      
      if (targetMessageId) {
        console.log("📄 Reducer updating message", targetMessageId, "with response:", action.response.slice(0, 50));
        
        // Update the message content and set reasoning data
        return {
          ...state,
          messages: state.messages.map(m => 
            m.id.toString() === targetMessageId
              ? { 
                  ...m, 
                  content: action.response,
                  reasoning: action.reasoning || m.reasoning  // Use provided reasoning or keep existing
                }
              : m
          ),
          currentReasoningMessageId: state.currentReasoningMessageId === targetMessageId ? undefined : state.currentReasoningMessageId
        };
      } else {
        console.warn("⚠️ Reducer: Complete event received but no target message found");
        return state;
      }
    default:
      return state;
  }
}

// Helper function to map workflow types to endpoint names
function getEndpointNames(inputType?: string, outputType?: string): { inputEndpoint: string; outputEndpoint: string } {
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
}

const initialState: AppState = {
  conversations: [],
  messages: [],
  stage: "start",
  reasoningLog: [],
  wsConnected: false,
  currentReasoningMessageId: undefined,
  showViz: false,
  showExecution: false,
  splitRatio: 0.5,
  verticalSplitRatio: 0.4, // 40% for propagation, 60% for execution
  graph: { allPaths: [], currentPaths: [], chosenPath: null, toolMetadata: [], colors: {}, positions: {}, reduceAnimationCompleted: false },
  console: [],
};

interface AppContextValue extends AppState {
  dispatch: React.Dispatch<Action>;
  connectSocket: (conversationId: string) => ConversationSocket;
}

const AppContext = createContext<AppContextValue | undefined>(undefined);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  // Generate a deterministic seed from currentConversationId/thread_id
  const getSeedFromThreadId = (threadId?: string): number | undefined => {
    if (!threadId) return undefined;
    let hash = 0;
    for (let i = 0; i < threadId.length; i++) {
      hash = (hash * 131 + threadId.charCodeAt(i)) >>> 0;
    }
    return hash & 0xFFFFFFFF; // Match GUI implementation
  };

  const value = useMemo<AppContextValue>(() => {
    function connectSocket(conversationId: string): ConversationSocket {
      const socket = new ConversationSocket(conversationId, {
        onOpen: () => dispatch({ type: "ws_status", connected: true }),
        onClose: () => dispatch({ type: "ws_status", connected: false }),
        onEvent: (ev: BackendEvent) => {
          console.log("🔌 WebSocket event received:", ev);
          
          if ((ev as any).event === "reasoning") {
            const d = ev as any;
            console.log("💭 REASONING EVENT RECEIVED:", {
              event: d.event,
              timestamp: d.timestamp,
              frontend_message_id: d.frontend_message_id,
              data: d.data,
              reasoning_content: d.data?.reasoning || d.data?.reasoning_content,
              node: d.data?.node
            });
            
            // Handle both old reasoning log and new message-specific reasoning
            dispatch({
              type: "append_reasoning",
              entry: { timestamp: d.timestamp, text: d.data?.reasoning ?? "", node: d.data?.node },
            });
            
            // Start reasoning if not already started and we have reasoning content
            if (d.data?.reasoning && !state.currentReasoningMessageId && state.messages.length > 0) {
              // Find the most recent assistant message to attach reasoning to
              const lastAssistantMessage = [...state.messages].reverse().find(m => m.role === 'assistant');
              if (lastAssistantMessage) {
                console.log("🎯 Starting reasoning for message:", lastAssistantMessage.id);
                dispatch({
                  type: "start_reasoning",
                  messageId: lastAssistantMessage.id.toString()
                });
              }
            }
            
            // If there's a current reasoning message, update it
            if (state.currentReasoningMessageId) {
              console.log("📝 Updating reasoning content:", d.data?.reasoning?.slice(0, 50));
              dispatch({
                type: "update_reasoning",
                messageId: state.currentReasoningMessageId,
                reasoning: d.data?.reasoning ?? "",
                isComplete: d.data?.complete || false
              });
              
              if (d.data?.complete) {
                dispatch({
                  type: "complete_reasoning",
                  messageId: state.currentReasoningMessageId,
                  thinkingTime: d.data?.thinking_time
                });
              }
            }
            // New: also route reasoning into workflow sections when node is present
            const node: string | undefined = d.data?.node;
            const stageTitles: Record<string, string> = {
              classify: "Classifying...",
              find_path: "Searching for possible paths...",
              route: "Selecting the path...",
              execute: "Executing...",
              finalize: "Formatting response...",
            };
            const fmId = d.frontend_message_id || state.currentReasoningMessageId;
            if (fmId && node) {
              // Ensure a section exists
              const title = stageTitles[node] || node;
              dispatch({ type: "workflow_start_stage", messageId: fmId, node, title, status: title, startedAt: d.timestamp });
              // Append reasoning chunk if provided
              if (d.data?.reasoning) {
                dispatch({ type: "workflow_update_reasoning", messageId: fmId, node, text: String(d.data.reasoning) });
              }
              // Handle clarifications
              const clarify = d.data?.clarification || d.data?.clarify;
              if (clarify) {
                dispatch({ type: "workflow_clarification", messageId: fmId, node, text: String(clarify) });
              }
              // Mark completion for stage if indicated
              if (d.data?.complete) {
                const time = typeof d.data?.thinking_time === 'number' ? d.data.thinking_time : undefined;
                dispatch({ type: "workflow_complete_stage", messageId: fmId, node, thinkingTime: time, completedAt: d.timestamp });
              }
            }
          } else if ((ev as any).event === "message_start") {
            // New message started - could include reasoning
            const d = ev as any;
            if (d.data?.message_id && d.data?.has_reasoning) {
              dispatch({
                type: "start_reasoning",
                messageId: d.data.message_id.toString()
              });
            }
          } else if ((ev as any).event === "state_update") {
            const d = ev as any;
            const node: string | undefined = d.data?.node || d.data?.next_node;
            if (node) {
              const stage = node as Stage;
              if (
                stage === "start" ||
                stage === "classify" ||
                stage === "find_path" ||
                stage === "route" ||
                stage === "execute" ||
                stage === "finalize" ||
                stage === "waiting_for_feedback"
              ) {
                dispatch({ type: "set_stage", stage });
                if (stage === 'execute') {
                  dispatch({ type: "set_show_viz", show: true });
                  dispatch({ type: "set_show_execution", show: true });
                }
                if (stage === 'route') {
                  try {
                    console.log("[Route] state_update received: entering route stage", {
                      frontendMessageId: d.frontend_message_id,
                      hasChosenPath: Array.isArray(d.data?.state_update?.chosen_path) && d.data?.state_update?.chosen_path.length > 0,
                      allPathsCount: Array.isArray(d.data?.state_update?.all_paths) ? d.data.state_update.all_paths.length : 0,
                      animation: state.graph.animation,
                    });
                  } catch {}
                }
              }
            }
            // Ensure propagation panel opens when next_node === 'find_path'
            if (d.data?.next_node === 'find_path') {
              dispatch({ type: "ui/open_panel", id: 'propagation' });
            }
            // New: Create or update workflow stage block on state transitions
            try {
              const fmId = d.frontend_message_id || state.currentReasoningMessageId;
              const stageNode: string | undefined = d.data?.node || d.data?.next_node;
              const titles: Record<string, string> = {
                classify: "Classifying...",
                find_path: "Searching for possible paths...",
                route: "Selecting the path...",
                execute: "Executing...",
                finalize: "Formatting response...",
              };
              if (fmId && stageNode) {
                const title = titles[stageNode] || stageNode;
                dispatch({ type: "workflow_start_stage", messageId: fmId, node: stageNode, title, status: title });
                // If route provided a chosen_path, ensure find_path title is present
                const chosen = d.data?.state_update?.chosen_path;
                if (stageNode === 'route' && Array.isArray(chosen) && chosen.length > 0) {
                  const fpTitle = titles['find_path'] || 'find_path';
                  dispatch({ type: "workflow_start_stage", messageId: fmId, node: 'find_path', title: fpTitle, status: fpTitle });
                }
                // Add clarifications if present in state update
                const clarification = d.data?.state_update?.classify_clarification || d.data?.state_update?.route_clarification;
                if (clarification) {
                  dispatch({ type: "workflow_clarification", messageId: fmId, node: stageNode, text: String(clarification) });
                }
              }
            } catch {}
            // Populate Propagation whenever paths are present (route may have chosen_path)
            const update = d.data?.state_update;
            if (update) {
              const allPathsRaw = (update.all_paths || []) as any[];
              const chosenPathRaw = (update.chosen_path || null) as any | null;
              const toolMetadata = (update.tool_metadata || []) as Array<Record<string, unknown>>;
              
              // Extract workflow types from state_update (fallback to type_savepoint if output_type missing)
              const inputType = update.input_type as string | undefined;
              const outputType = (update.output_type as string | undefined) 
                || (Array.isArray(update.type_savepoint) && update.type_savepoint.length > 0 
                      ? (update.type_savepoint[update.type_savepoint.length - 1] as string | undefined) 
                      : undefined);
              
              // Skip if we don't have any paths
              if (!allPathsRaw.length && !chosenPathRaw) return;
              
              try {
                console.log(`[Viz] state_update(${d.data?.node}) received`, {
                  inputType,
                  outputType,
                  allPathsCount: allPathsRaw.length,
                  hasChosenPath: !!chosenPathRaw,
                });
                if (d.data?.node === 'route') {
                  console.log('[Route] details', {
                    chosenPathRaw,
                    allPathsRawCount: allPathsRaw.length,
                  });
                }
              } catch {}
              
              const toTokens = (p: any): string[] => {
                if (Array.isArray(p)) {
                  return p.map((s: any) => {
                    if (typeof s === "string") return s;
                    // Handle PathItem objects from database
                    if (s?.name) return s.name;
                    // Handle nested arrays (all_paths structure)
                    if (Array.isArray(s)) {
                      return s.map((item: any) => item?.name || "tool");
                    }
                    return "tool";
                  }).flat();
                }
                if (p && typeof p === "object") {
                  const steps = p.steps || p.tool_metadata || [];
                  return Array.isArray(steps) ? steps.map((s: any) => s?.name || "tool") : [];
                }
                return [];
              };
              
              const tokenPaths = allPathsRaw.map(toTokens).filter((arr) => arr.length > 0);
              const chosenTokenPath = chosenPathRaw ? toTokens(chosenPathRaw) : null;

              // If we're in route clarifying (no chosen path yet), do not start reduce or rehydrate; keep existing graph
              if ((d.data?.node === 'route') && tokenPaths.length === 0 && !chosenTokenPath) {
                try { console.log('[Route] Clarification update without chosen_path; holding graph'); } catch {}
                return;
              }

              if (tokenPaths.length > 0) {
                try { console.log("[Viz] tokenPaths (state_update)", tokenPaths); } catch {}
                dispatch({ type: "hydrate_graph", allPaths: tokenPaths, toolMetadata, chosenPath: chosenTokenPath, inputType, outputType });

                // Get dynamic endpoint names
                const { inputEndpoint, outputEndpoint } = getEndpointNames(inputType, outputType);

                // Calculate positions and colors based on all unique nodes
                const endpointTypes = ["IMAGE_IN", "IMAGE_OUT", "AUDIO_IN", "AUDIO_OUT", "VIDEO_IN", "VIDEO_OUT", "TEXT_IN", "TEXT_OUT", "FILE_IN", "FILE_OUT", "IMG"];
                const allNodes = toolMetadata.length > 0
                  ? Array.from(new Set(toolMetadata.map((t: any) => t.name || "tool")))
                  : Array.from(new Set(tokenPaths.flat().filter((t) => !endpointTypes.includes(t))));

                // Include dynamic endpoint nodes in the nodes list
                const nodesWithEndpoints = Array.from(new Set([...allNodes, inputEndpoint, outputEndpoint]));

                // Generate seed from current conversation/thread ID
                const seed = getSeedFromThreadId(state.currentConversationId);
                const colors = ensureColors(nodesWithEndpoints, state.graph.colors, seed);
                const positions = calculateNodePositions(toolMetadata, tokenPaths, 460, 360, state.graph.positions, 64, 20, seed);

                console.log("[Viz] Calculated positions for nodes:", Object.keys(positions));

                dispatch({ type: "set_graph_style", colors, positions });
                dispatch({ type: "start_population" });
                // Always open the panel when paths are present
                dispatch({ type: "ui/open_panel", id: 'propagation' });
                dispatch({ type: "set_show_viz", show: true });
                if ((d.data?.node || d.data?.next_node) === 'execute') {
                  dispatch({ type: "set_show_execution", show: true });
                }
              } else if (chosenTokenPath && chosenTokenPath.length > 0) {
                // Only update chosen path; do NOT collapse allPaths or reset animations
                dispatch({ type: "set_chosen_path", chosenPath: chosenTokenPath });
                dispatch({ type: "ui/open_panel", id: 'propagation' });
                dispatch({ type: "set_show_viz", show: true });
              }
            }
          } else if ((ev as any).type === "state_checkpoint") {
            const d = ev as any;
            if (d.state_uid) {
              getState(d.state_uid, true)
                .then((s) => {
                  dispatch({ type: "set_state", state: s });
                  // Hydrate graph if this checkpoint contains path info (find_path or route)
                  try {
                    const node = (s as any)?.node || (s as any)?.next_node;
                    try { console.log("[Viz] state_checkpoint fetched node=", node); } catch {}
                    const allPaths = ((s as any)?.all_paths || []) as any[];
                    const chosenPath = ((s as any)?.chosen_path || null) as any | null;
                    const toolMeta = ((s as any)?.tool_metadata || []) as Array<Record<string, unknown>>;
                    const inputType = (s as any)?.input_type as string | undefined;
                    const outputType = (s as any)?.output_type as string | undefined 
                      || (Array.isArray((s as any)?.type_savepoint) && (s as any)?.type_savepoint.length > 0
                            ? (s as any)?.type_savepoint[(s as any)?.type_savepoint.length - 1] as string | undefined
                            : undefined);
                    
                    if ((node === "find_path" || node === "route") && (allPaths.length || chosenPath || toolMeta.length)) {
                      // If we're in route and there is no chosen_path yet (e.g., clarifying), hold current graph
                      if (node === 'route' && (!Array.isArray(chosenPath) || chosenPath.length === 0)) {
                        try { console.log("[Viz] route checkpoint without chosen_path; holding graph (no rehydrate)"); } catch {}
                        return;
                      }
                      const toTokens = (p: any): string[] => {
                        if (Array.isArray(p)) return p.map((s: any) => (typeof s === "string" ? s : s?.name || "tool"));
                        if (p && typeof p === "object") {
                          const steps = p.steps || p.tool_metadata || [];
                          return Array.isArray(steps) ? steps.map((s: any) => s?.name || "tool") : [];
                        }
                        return [];
                      };
                      
                      const tokenPaths = allPaths.map(toTokens).filter((arr) => arr.length > 0);
                      const chosenTokenPath = chosenPath ? toTokens(chosenPath) : null;

                      try { console.log("[Viz] tokenPaths (checkpoint)", tokenPaths); } catch {}
                      if (tokenPaths.length) {
                        dispatch({ type: "hydrate_graph", allPaths: tokenPaths, toolMetadata: toolMeta, chosenPath: chosenTokenPath, inputType, outputType });

                        // Get dynamic endpoint names
                        const { inputEndpoint, outputEndpoint } = getEndpointNames(inputType, outputType);

                        // Calculate positions and colors based on all unique nodes
                        const endpointTypes = ["IMAGE_IN", "IMAGE_OUT", "AUDIO_IN", "AUDIO_OUT", "VIDEO_IN", "VIDEO_OUT", "TEXT_IN", "TEXT_OUT", "FILE_IN", "FILE_OUT", "IMG"];
                        const allNodes = toolMeta.length > 0
                          ? Array.from(new Set(toolMeta.map((t: any) => t.name || "tool")))
                          : Array.from(new Set(tokenPaths.flat().filter((t) => !endpointTypes.includes(t))));

                        // Include dynamic endpoint nodes in the nodes list
                        const nodesWithEndpoints = Array.from(new Set([...allNodes, inputEndpoint, outputEndpoint]));

                        // Generate seed from current conversation/thread ID
                        const seed = getSeedFromThreadId(state.currentConversationId);
                        const colors = ensureColors(nodesWithEndpoints, state.graph.colors, seed);
                        const positions = calculateNodePositions(toolMeta, tokenPaths, 460, 360, state.graph.positions, 64, 20, seed);

                        console.log("[Viz] (checkpoint) Calculated positions for nodes:", Object.keys(positions));

                        dispatch({ type: "set_graph_style", colors, positions });
                        dispatch({ type: "start_population" });
                        dispatch({ type: "set_show_viz", show: true });
                        // Ensure execution panel is revealed if we're in execute
                        if (node === 'execute') {
                          dispatch({ type: "set_show_execution", show: true });
                        }
                        try { console.log("[Viz] graph hydrated & showViz=true"); } catch {}
                      } else if (chosenTokenPath && chosenTokenPath.length > 0) {
                        // Only update chosen path; do NOT collapse allPaths or reset animations
                        dispatch({ type: "set_chosen_path", chosenPath: chosenTokenPath });
                        dispatch({ type: "set_show_viz", show: true });
                      }
                    }
                  } catch {}
                })
                .catch(() => void 0);
            }
          } else if ((ev as any).type === "complete") {
            // End of processing - use frontend_message_id for precise targeting
            const d = ev as any;
            console.log("✅ Processing complete event:", d);
            
            // Extract response, reasoning, and frontend message ID
            const response = d.result?.response || d.response || "Response completed";
            const reasoning = d.result?.reasoning || null;
            const frontendMessageId = d.frontend_message_id;
            
            console.log("🎯 Complete event with frontend_message_id:", frontendMessageId);
            console.log("🧠 Complete event with reasoning:", reasoning ? "Yes" : "No");
            
            // Dispatch to reducer with response and reasoning
            dispatch({
              type: "handle_completion",
              response: response,
              reasoning: reasoning,
              messageId: frontendMessageId
            });
            // New: mark finalize stage completed and set its thinking time if available
            if (frontendMessageId) {
              const tt = reasoning?.thinking_time as number | undefined;
              dispatch({ type: "workflow_complete_stage", messageId: frontendMessageId, node: "finalize", thinkingTime: tt });
            }

            // If current conversation title is still default, set it from the complete state's objective
            const currentConv = state.conversations.find(c => c.id === state.currentConversationId);
            const isDefaultTitle = !currentConv || !currentConv.title || currentConv.title === "New Conversation";
            const stateUid: string | undefined = d.result?.state_uid;
            if (isDefaultTitle && stateUid && state.currentConversationId) {
              getState(stateUid, true)
                .then((s: StateResponse) => {
                  const obj = (s as any)?.objective;
                  if (typeof obj === "string" && obj.trim()) {
                    return updateConversation(state.currentConversationId as string, obj.trim());
                  }
                })
                .then((updated?: ConversationResponse) => {
                  if (updated) {
                    dispatch({ type: "upsert_conversation", conversation: updated });
                  }
                })
                .catch(() => void 0);
            }
          } else if ((ev as any).type === "conversation_updated") {
            const d = ev as any;
            if (d.conversation) {
              dispatch({ type: "upsert_conversation", conversation: d.conversation });
            }
          } else if ((ev as any).event === "execution_event") {
            const d = ev as any;
            const status = d.data?.status;
            if (status === "stdout_line" || status === "stderr_line") {
              const t: 'stdout' | 'stderr' = status === 'stdout_line' ? 'stdout' : 'stderr';
              dispatch({ type: "append_console_line", entry: { timestamp: d.timestamp, type: t, line: String(d.data?.line || ""), step_index: d.data?.step_index, tool_name: d.data?.tool_name } });
              // Also track current executing node for UI highlighting
              if (typeof d.data?.step_index === 'number' || typeof d.data?.tool_name === 'string') {
                dispatch({ type: "set_current_execution", step_index: d.data?.step_index, tool_name: d.data?.tool_name });
              }
              dispatch({ type: "set_show_viz", show: true });
              dispatch({ type: "set_show_execution", show: true });
            } else if (status === "file_saved") {
              dispatch({ type: "file_saved", file: { path: String(d.data?.path || ""), mime: d.data?.mime, tool_name: d.data?.tool_name, step_index: d.data?.step_index } });
              // Update execution pointer as file save often corresponds to a step
              if (typeof d.data?.step_index === 'number' || typeof d.data?.tool_name === 'string') {
                dispatch({ type: "set_current_execution", step_index: d.data?.step_index, tool_name: d.data?.tool_name });
              }
              dispatch({ type: "set_show_viz", show: true });
              dispatch({ type: "set_show_execution", show: true });
            } else if (status === "execution_step_complete") {
              if (typeof d.data?.step_index === 'number' && d.data?.tool_name) {
                dispatch({ type: "execution_step_complete", step_index: d.data.step_index, tool_name: d.data.tool_name });
              }
              dispatch({ type: "set_show_viz", show: true });
              dispatch({ type: "set_show_execution", show: true });
            }
          }
        },
      });
      socket.connect();
      return socket;
    }

    return { ...state, dispatch, connectSocket };
  }, [state]);

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}


