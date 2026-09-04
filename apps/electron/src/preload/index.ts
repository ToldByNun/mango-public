import { contextBridge, ipcRenderer, webUtils } from "electron";
import type { AgentEvent } from "../shared/events";
import type { MangoBridge } from "../shared/ipc-schema";

const mango: MangoBridge = {
  sessions: {
    list: () => ipcRenderer.invoke("sessions:list"),
    save: (sessions) => ipcRenderer.invoke("sessions:save", sessions),
  },
  workspace: {
    get: () => ipcRenderer.invoke("workspace:get"),
    pick: () => ipcRenderer.invoke("workspace:pick"),
    set: (path) => ipcRenderer.invoke("workspace:set", path),
    branch: () => ipcRenderer.invoke("workspace:branch"),
  },
  files: {
    pick: () => ipcRenderer.invoke("files:pick"),
  },
  sidecar: {
    status: () => ipcRenderer.invoke("sidecar:status"),
    load: () => ipcRenderer.invoke("sidecar:load"),
    settings: () => ipcRenderer.invoke("sidecar:settings"),
    setModelPath: (path) => ipcRenderer.invoke("sidecar:set-model-path", path),
    updateSettings: (settings) => ipcRenderer.invoke("sidecar:update-settings", settings),
    selectModel: (path) => ipcRenderer.invoke("sidecar:select-model", path),
  },
  models: {
    list: () => ipcRenderer.invoke("models:list"),
  },
  agent: {
    run: (
      sessionId,
      goal,
      workspace,
      generateTitle,
      thinkingLevel,
      thoughtMaxTokens,
      mode,
    ) =>
      ipcRenderer.invoke("agent:run", {
        sessionId,
        goal,
        workspace,
        generateTitle,
        thinkingLevel,
        thoughtMaxTokens,
        mode,
      }),
    cancel: (sessionId) => ipcRenderer.invoke("agent:cancel", sessionId),
    continueStall: (sessionId) => ipcRenderer.invoke("agent:continueStall", sessionId),
    undoLastMutation: (sessionId) => ipcRenderer.invoke("agent:undoLastMutation", sessionId),
    onEvent: (handler) => {
      const listener = (_event: unknown, payload: AgentEvent): void => handler(payload);
      ipcRenderer.on("agent:event", listener);
      return () => ipcRenderer.removeListener("agent:event", listener);
    },
    onSidecarError: (handler) => {
      const listener = (_event: unknown, message: string): void => handler(message);
      ipcRenderer.on("sidecar:error", listener);
      return () => ipcRenderer.removeListener("sidecar:error", listener);
    },
  },
  app: {
    openPath: (target) => ipcRenderer.invoke("app:open-path", target),
    configPath: () => ipcRenderer.invoke("app:config-path"),
    version: () => ipcRenderer.invoke("app:version"),
    checkUpdates: () => ipcRenderer.invoke("app:check-updates"),
  },
  win: {
    minimize: () => {
      ipcRenderer.send("win:minimize");
    },
    maximize: () => {
      ipcRenderer.send("win:maximize");
    },
    close: () => {
      ipcRenderer.send("win:close");
    },
  },
  getPathForFile: (file) => webUtils.getPathForFile(file),
  github: {
    status: () => ipcRenderer.invoke("github:status"),
    login: () => ipcRenderer.invoke("github:login"),
    logout: () => ipcRenderer.invoke("github:logout"),
    onDeviceCode: (handler) => {
      const listener = (
        _event: unknown,
        payload: { userCode: string; verificationUri: string },
      ): void => handler(payload);
      ipcRenderer.on("github:device-code", listener);
      return () => ipcRenderer.removeListener("github:device-code", listener);
    },
  },
  speech: {
    start: (locale) => ipcRenderer.invoke("speech:start", locale),
    stop: () => ipcRenderer.invoke("speech:stop"),
    onResult: (handler) => {
      const listener = (_event: unknown, payload: { text: string }): void => handler(payload.text);
      ipcRenderer.on("speech:result", listener);
      return () => ipcRenderer.removeListener("speech:result", listener);
    },
    onError: (handler) => {
      const listener = (_event: unknown, payload: { message: string }): void =>
        handler(payload.message);
      ipcRenderer.on("speech:error", listener);
      return () => ipcRenderer.removeListener("speech:error", listener);
    },
  },
};

contextBridge.exposeInMainWorld("mango", mango);
