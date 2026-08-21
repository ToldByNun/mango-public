import { contextBridge, ipcRenderer, webUtils } from "electron";
import type { AgentEvent, Session } from "../shared/events";

contextBridge.exposeInMainWorld("mango", {
  sessions: {
    list: (): Promise<Session[]> => ipcRenderer.invoke("sessions:list"),
    save: (sessions: Session[]): Promise<Session[]> => ipcRenderer.invoke("sessions:save", sessions),
  },
  workspace: {
    get: (): Promise<string> => ipcRenderer.invoke("workspace:get"),
    pick: (): Promise<string> => ipcRenderer.invoke("workspace:pick"),
    set: (path: string): Promise<string> => ipcRenderer.invoke("workspace:set", path),
    branch: (): Promise<string> => ipcRenderer.invoke("workspace:branch"),
  },
  files: {
    pick: (): Promise<string[]> => ipcRenderer.invoke("files:pick"),
  },
  sidecar: {
    status: (): Promise<{ ready: boolean; modelLoaded: boolean }> => ipcRenderer.invoke("sidecar:status"),
    load: (): Promise<Record<string, unknown>> => ipcRenderer.invoke("sidecar:load"),
    settings: (): Promise<Record<string, unknown>> => ipcRenderer.invoke("sidecar:settings"),
    setModelPath: (path: string): Promise<Record<string, unknown>> =>
      ipcRenderer.invoke("sidecar:set-model-path", path),
    selectModel: (path: string): Promise<Record<string, unknown>> =>
      ipcRenderer.invoke("sidecar:select-model", path),
  },
  models: {
    list: (): Promise<Array<{ path: string; label: string }>> => ipcRenderer.invoke("models:list"),
  },
  agent: {
    run: (
      sessionId: string,
      goal: string,
      workspace?: string,
      generateTitle?: boolean,
      thinkingLevel?: string,
    ): Promise<Record<string, unknown>> =>
      ipcRenderer.invoke("agent:run", { sessionId, goal, workspace, generateTitle, thinkingLevel }),
    cancel: (sessionId: string): Promise<Record<string, unknown>> =>
      ipcRenderer.invoke("agent:cancel", sessionId),
    onEvent: (handler: (event: AgentEvent) => void): (() => void) => {
      const listener = (_event: unknown, payload: AgentEvent): void => handler(payload);
      ipcRenderer.on("agent:event", listener);
      return () => ipcRenderer.removeListener("agent:event", listener);
    },
    onSidecarError: (handler: (message: string) => void): (() => void) => {
      const listener = (_event: unknown, message: string): void => handler(message);
      ipcRenderer.on("sidecar:error", listener);
      return () => ipcRenderer.removeListener("sidecar:error", listener);
    },
  },
  app: {
    openPath: (target: string): Promise<void> => ipcRenderer.invoke("app:open-path", target),
    configPath: (): Promise<string> => ipcRenderer.invoke("app:config-path"),
    version: (): Promise<string> => ipcRenderer.invoke("app:version"),
    checkUpdates: (): Promise<{ ok: boolean; message: string }> => ipcRenderer.invoke("app:check-updates"),
  },
  win: {
    minimize: (): void => { ipcRenderer.send("win:minimize"); },
    maximize: (): void => { ipcRenderer.send("win:maximize"); },
    close: (): void => { ipcRenderer.send("win:close"); },
  },
  getPathForFile: (file: File): string => webUtils.getPathForFile(file),
  github: {
    status: (): Promise<{ loggedIn: boolean; user?: { login: string; avatar_url: string; name: string | null } }> =>
      ipcRenderer.invoke("github:status"),
    login: (): Promise<{ loggedIn: boolean; user?: { login: string; avatar_url: string; name: string | null } }> =>
      ipcRenderer.invoke("github:login"),
    logout: (): Promise<{ loggedIn: boolean }> => ipcRenderer.invoke("github:logout"),
    onDeviceCode: (handler: (data: { userCode: string; verificationUri: string }) => void): (() => void) => {
      const listener = (_event: unknown, payload: { userCode: string; verificationUri: string }): void => handler(payload);
      ipcRenderer.on("github:device-code", listener);
      return () => ipcRenderer.removeListener("github:device-code", listener);
    },
  },
  speech: {
    start: (locale?: string): Promise<{ ok: boolean; listening: boolean }> =>
      ipcRenderer.invoke("speech:start", locale),
    stop: (): Promise<{ ok: boolean }> => ipcRenderer.invoke("speech:stop"),
    onResult: (handler: (text: string) => void): (() => void) => {
      const listener = (_event: unknown, payload: { text: string }): void => handler(payload.text);
      ipcRenderer.on("speech:result", listener);
      return () => ipcRenderer.removeListener("speech:result", listener);
    },
    onError: (handler: (message: string) => void): (() => void) => {
      const listener = (_event: unknown, payload: { message: string }): void => handler(payload.message);
      ipcRenderer.on("speech:error", listener);
      return () => ipcRenderer.removeListener("speech:error", listener);
    },
  },
});
