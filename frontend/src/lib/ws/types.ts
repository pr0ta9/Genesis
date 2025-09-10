export type Stage =
  | "start"
  | "classify"
  | "find_path"
  | "route"
  | "execute"
  | "finalize"
  | "waiting_for_feedback";

export interface StageEventPayload {
  node?: string;
  next_node?: string;
}


