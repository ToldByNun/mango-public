import type { AgentEvent, Session } from "@shared/events";

export type GgufModel = { path: string; label: string };

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
    status: () => Promise<{ ready: boolean; modelLoaded: boolean }>;
    load: () => Promise<Record<string, unknown>>;
    settings: () => Promise<Record<string, unknown>>;
    setModelPath: (path: string) => Promise<Record<string, unknown>>;
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
    ) => Promise<Record<string, unknown>>;
    cancel: (sessionId: string) => Promise<Record<string, unknown>>;
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
    status: () => Promise<{ loggedIn: boolean; user?: { login: string; avatar_url: string; name: string | null } }>;
    login: () => Promise<{ loggedIn: boolean; user?: { login: string; avatar_url: string; name: string | null } }>;
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

declare global {
  interface Window {
    mango: MangoBridge;
  }
}

export {};
