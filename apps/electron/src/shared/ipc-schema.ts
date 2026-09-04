/**
 * Zero-trust IPC contract — schemas + typed bridge (default_ex.md pattern).
 * Every ipcMain.handle must parse inputs with these schemas before services run.
 */
import { z } from "zod";
import type { AgentEvent, Session } from "./events";

export const ThinkingLevelSchema = z.enum(["off", "think", "deep", "max"]);
export type ThinkingLevel = z.infer<typeof ThinkingLevelSchema>;

export const SessionStatusSchema = z.enum(["idle", "running", "stopped", "error"]);

const TranscriptBlockSchema = z
  .object({
    id: z.string(),
    kind: z.string(),
    createdAt: z.number(),
  })
  .passthrough();

export const SessionSchema = z
  .object({
    id: z.string().min(1),
    title: z.string(),
    workspace: z.string(),
    createdAt: z.number(),
    updatedAt: z.number(),
    messages: z.array(TranscriptBlockSchema),
    status: SessionStatusSchema,
  })
  .passthrough();

export const SessionsSaveSchema = z.array(SessionSchema);

export const WorkspaceSetSchema = z.object({
  path: z.string().min(1),
});

export const PathStringSchema = z.string().min(1);

export const AgentRunSchema = z.object({
  sessionId: z.string().min(1),
  goal: z.string().min(1),
  workspace: z.string().optional(),
  generateTitle: z.boolean().optional(),
  thinkingLevel: ThinkingLevelSchema.or(z.string()).optional(),
  thoughtMaxTokens: z.number().nullable().optional(),
  mode: z.string().optional(),
});

export const SessionIdSchema = z.string().min(1);

export const SidecarUpdateSettingsSchema = z.record(z.unknown());

export const ModelPathSchema = z.object({
  path: z.string().min(1),
});

/** Loose wrapper when invoke passes a bare string path */
export const ModelPathInputSchema = z.union([
  z.string().min(1),
  ModelPathSchema,
]);

export const SpeechStartSchema = z.string().optional();

export const GgufModelSchema = z.object({
  path: z.string(),
  label: z.string(),
});

export const SidecarStatusSchema = z.object({
  ready: z.boolean(),
  modelLoaded: z.boolean(),
  error: z.string().optional(),
});

export const GithubUserSchema = z.object({
  login: z.string(),
  avatar_url: z.string(),
  name: z.string().nullable(),
});

export const GithubStatusSchema = z.object({
  loggedIn: z.boolean(),
  user: GithubUserSchema.optional(),
  error: z.string().optional(),
});

export const CheckUpdatesSchema = z.object({
  ok: z.boolean(),
  message: z.string(),
});

export type AgentRunInput = z.infer<typeof AgentRunSchema>;
export type WorkspaceSetInput = z.infer<typeof WorkspaceSetSchema>;
export type GgufModel = z.infer<typeof GgufModelSchema>;
export type SidecarStatus = z.infer<typeof SidecarStatusSchema>;
export type GithubStatus = z.infer<typeof GithubStatusSchema>;

export function parseModelPath(raw: unknown): string {
  const parsed = ModelPathInputSchema.parse(raw);
  return typeof parsed === "string" ? parsed : parsed.path;
}

/** Typed facade exposed on window.mango via preload */
export type MangoBridge = {
  sessions: {
    list: () => Promise<Session[]>;
    save: (sessions: Session[]) => Promise<Session[]>;
  };
  workspace: {
    get: () => Promise<string>;
    pick: () => Promise<string>;
    set: (path: string) => Promise<string>;
    branch: () => Promise<string>;
  };
  files: {
    pick: () => Promise<string[]>;
  };
  sidecar: {
    status: () => Promise<SidecarStatus>;
    load: () => Promise<Record<string, unknown>>;
    settings: () => Promise<Record<string, unknown>>;
    setModelPath: (path: string) => Promise<Record<string, unknown>>;
    updateSettings: (settings: Record<string, unknown>) => Promise<Record<string, unknown>>;
    selectModel: (path: string) => Promise<Record<string, unknown>>;
  };
  models: {
    list: () => Promise<GgufModel[]>;
  };
  agent: {
    run: (
      sessionId: string,
      goal: string,
      workspace?: string,
      generateTitle?: boolean,
      thinkingLevel?: string,
      thoughtMaxTokens?: number | null,
      mode?: string,
    ) => Promise<Record<string, unknown>>;
    cancel: (sessionId: string) => Promise<Record<string, unknown>>;
    continueStall: (sessionId: string) => Promise<Record<string, unknown>>;
    undoLastMutation: (sessionId: string) => Promise<Record<string, unknown>>;
    onEvent: (handler: (event: AgentEvent) => void) => () => void;
    onSidecarError: (handler: (message: string) => void) => () => void;
  };
  app: {
    openPath: (target: string) => Promise<void>;
    configPath: () => Promise<string>;
    version: () => Promise<string>;
    checkUpdates: () => Promise<{ ok: boolean; message: string }>;
  };
  win: {
    minimize: () => void;
    maximize: () => void;
    close: () => void;
  };
  getPathForFile: (file: File) => string;
  github: {
    status: () => Promise<GithubStatus>;
    login: () => Promise<GithubStatus>;
    logout: () => Promise<{ loggedIn: boolean }>;
    onDeviceCode: (handler: (data: { userCode: string; verificationUri: string }) => void) => () => void;
  };
  speech: {
    start: (locale?: string) => Promise<{ ok: boolean; listening: boolean }>;
    stop: () => Promise<{ ok: boolean }>;
    onResult: (handler: (text: string) => void) => () => void;
    onError: (handler: (message: string) => void) => () => void;
  };
};

export function ipcError(channel: string, error: unknown): Error {
  console.error(`IPC Validation Error [${channel}]:`, error);
  if (error instanceof z.ZodError) {
    return new Error(`Invalid payload for ${channel}`);
  }
  return error instanceof Error ? error : new Error(String(error));
}
