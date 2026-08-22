export declare const AGENT_EVENTS: readonly [
  "agent.started",
  "agent.title",
  "agent.thought",
  "agent.token",
  "agent.tool",
  "agent.file",
  "agent.verification",
  "agent.syntax",
  "agent.experiment",
  "agent.final",
  "agent.stopped",
  "agent.error",
  "model.loaded",
  "model.unloaded",
];
export type AgentEventName = (typeof AGENT_EVENTS)[number];
export type AgentEvent = {
  event: AgentEventName;
  session_id: string;
  payload: Record<string, unknown>;
};
export type FileAction = "edited" | "read" | "created";
export type TranscriptBlock =
  | { id: string; kind: "user"; text: string; createdAt: number }
  | {
      id: string;
      kind: "thought";
      durationMs: number;
      text: string;
      streaming?: boolean;
      createdAt: number;
    }
  | {
      id: string;
      kind: "summary";
      edited: number;
      read: number;
      verify?: "pass" | "fail";
      createdAt: number;
    }
  | {
      id: string;
      kind: "file";
      action: FileAction;
      path: string;
      absolutePath?: string;
      added?: number;
      removed?: number;
      startLine?: number;
      endLine?: number;
      diff?: string;
      createdAt: number;
    }
  | { id: string; kind: "status"; text: string; streaming?: boolean; createdAt: number }
  | {
      id: string;
      kind: "tool";
      title: string;
      name?: string;
      body?: string;
      console?: boolean;
      ok?: boolean;
      blocked?: boolean;
      streaming?: boolean;
      createdAt: number;
    }
  | { id: string; kind: "verification"; ok: boolean; report: string; createdAt: number }
  | { id: string; kind: "syntax"; path: string; message: string; createdAt: number }
  | {
      id: string;
      kind: "experiment";
      hypothesis: string;
      before?: number;
      after?: number;
      unit: string;
      decision: "keep" | "revert";
      deltaPct?: number;
      reason: string;
      createdAt: number;
    }
  | { id: string; kind: "final"; text: string; streaming?: boolean; createdAt: number }
  | { id: string; kind: "error"; text: string; createdAt: number };
export type SessionStatus = "idle" | "running" | "stopped" | "error";
export type Session = {
  id: string;
  title: string;
  workspace: string;
  createdAt: number;
  updatedAt: number;
  messages: TranscriptBlock[];
  status: SessionStatus;
};
export type AppSettings = {
  modelPath: string;
  temperature: number;
  topP: number;
  nCtx: number;
  modelName: string;
};
export type SidecarStatus = {
  ready: boolean;
  modelLoaded: boolean;
  error?: string;
};
export {};
