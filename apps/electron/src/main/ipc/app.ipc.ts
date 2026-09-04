import { app, ipcMain, shell } from "electron";
import type { IpcMainInvokeEvent } from "electron";
import { PathStringSchema, SpeechStartSchema, ipcError } from "../../shared/ipc-schema";
import { getStoredAuth, startDeviceFlow, clearAuth } from "../github";
import { speechActive, speechStart, speechStop } from "../speech";
import { checkForUpdatesManual } from "../updater";
import type { BrowserWindow } from "electron";

type SendFn = (channel: string, payload: unknown) => void;

export function registerAppIpc(deps: {
  runtimeConfigPath: string;
  getMainWindow: () => BrowserWindow | null;
  send: SendFn;
}): void {
  ipcMain.handle("app:open-path", async (_event, raw: unknown) => {
    try {
      const target = PathStringSchema.parse(raw);
      await shell.openPath(target);
    } catch (error) {
      throw ipcError("app:open-path", error);
    }
  });
  ipcMain.handle("app:config-path", () => deps.runtimeConfigPath);
  ipcMain.handle("app:version", () => app.getVersion());
  ipcMain.handle("app:check-updates", () => checkForUpdatesManual(deps.getMainWindow));

  ipcMain.handle("speech:start", (event: IpcMainInvokeEvent, raw: unknown) => {
    try {
      const locale = SpeechStartSchema.parse(raw);
      const ok = speechStart(
        locale && locale.length > 0 ? locale : "de-DE",
        (text) => event.sender.send("speech:result", { text }),
        (message) => event.sender.send("speech:error", { message }),
      );
      return { ok, listening: ok };
    } catch (error) {
      throw ipcError("speech:start", error);
    }
  });
  ipcMain.handle("speech:stop", () => {
    speechStop();
    return { ok: true };
  });
  ipcMain.handle("speech:status", () => ({ listening: speechActive() }));

  ipcMain.handle("github:status", () => {
    const auth = getStoredAuth();
    if (!auth) return { loggedIn: false };
    return { loggedIn: true, user: auth.user };
  });
  ipcMain.handle("github:login", async () => {
    const flow = await startDeviceFlow();
    if (!flow) return { loggedIn: false, error: "Failed to start GitHub login. Check Client ID." };
    deps.send("github:device-code", { userCode: flow.userCode, verificationUri: flow.verificationUri });
    const result = await flow.poll();
    if (result) return { loggedIn: true, user: result.user };
    return { loggedIn: false };
  });
  ipcMain.handle("github:logout", () => {
    clearAuth();
    return { loggedIn: false };
  });
}

export function registerWindowIpc(getMainWindow: () => BrowserWindow | null): void {
  ipcMain.on("win:minimize", () => getMainWindow()?.minimize());
  ipcMain.on("win:maximize", () => {
    const win = getMainWindow();
    if (win?.isMaximized()) win.unmaximize();
    else win?.maximize();
  });
  ipcMain.on("win:close", () => getMainWindow()?.close());
}
