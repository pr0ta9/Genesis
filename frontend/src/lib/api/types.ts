// Mirrors backend response models in backend/app/models/responses.py

export type ISODate = string; // ISO 8601

export interface ConversationResponse {
  id: string;
  title: string;
  created_at: ISODate;
  updated_at: ISODate;
  message_count: number;
}

export interface MessageResponse {
  id: number;
  conversation_id: string;
  role: string;
  content: string;
  attachments?: Array<{
    url: string; // absolute or API URL to preview
    name: string;
    mime: string;
    size?: number;
  }>;
  reasoning?: {
    content: string | any[];
    thinking_time?: number;
    is_expanded?: boolean;
    is_thinking?: boolean;
    additional_kwargs?: {
      reasoning_content?: string | any[];
      node_breakdown?: Array<{
        node: string;
        content: string;
        timestamp: string;
      }>;
      workflow_reasoning?: boolean;
    };
  } | null;
  // Optional per-stage workflow breakdown accumulated client-side
  workflow?: {
    sections: Array<{
      node: string; // e.g., classify, find_path, route, execute, finalize
      title: string; // Display title
      status: string; // e.g., "Classifying..."
      started_at?: string; // ISO
      completed_at?: string; // ISO
      thinking_time?: number; // seconds
      is_thinking?: boolean;
      reasoning_content?: string; // accumulated text
      clarification?: string | null; // any clarification under this stage
    }>;
  };
  state_id?: string | null;
  timestamp: ISODate;
  has_state: boolean;
}

export interface StateResponseBasic {
  uid: string;
  message_id: number;
  node?: string | null;
  next_node?: string | null;
  created_at: ISODate;
  has_execution: boolean;
  execution_instance?: string | null;
  is_complete?: boolean | null;
}

export interface StateResponseFull extends StateResponseBasic {
  objective?: string | null;
  input_type?: string | null;
  type_savepoint?: string[] | null;
  is_complex?: boolean | null;
  classify_reasoning?: string | null;
  classify_clarification?: string | null;
  tool_metadata?: Record<string, unknown>[] | null;
  all_paths?: Record<string, unknown>[] | null;
  chosen_path?: Record<string, unknown>[] | null;
  route_reasoning?: string | null;
  route_clarification?: string | null;
  is_partial?: boolean | null;
  execution_results?: Record<string, unknown> | null;
  execution_output_path?: string | null;
  response?: string | null;
  finalize_reasoning?: string | null;
  summary?: string | null;
  error_details?: string | null;
}

export type StateResponse = StateResponseBasic | StateResponseFull;

export interface MessageWithStateResponse extends MessageResponse {
  state?: StateResponse | null;
}

export interface ConversationDetailResponse {
  conversation: ConversationResponse;
  messages: MessageWithStateResponse[];
}

export interface SendMessageResponse {
  message: MessageResponse;
  response: string;
  state_uid?: string | null;
  has_clarification: boolean;
  clarification_type?: "classify" | "route" | null;
  execution_instance?: string | null;
}

export interface ModelResponse {
  id: string;
  name: string;
  provider: string;
}

export interface WorkspaceInfoResponse {
  project_root: string;
  tmp_root: string;
  output_root: string;
  tmp_directories: Array<Record<string, unknown>>;
  total_tmp_dirs: number;
  tmp_space_used: number;
  output_space_used: number;
}


