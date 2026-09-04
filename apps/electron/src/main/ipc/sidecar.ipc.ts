import { ipcMain } from "electron";
import { SidecarUpdateSettingsSchema, ipcError, parseModelPath } from "../../shared/ipc-schema";
import { listGgufModels } from "../models";
import type { SidecarService } from "../services/sidecar.service";

export function registerSidecarIpc(sidecar: SidecarService): void {
  ipcMain.handle("sidecar:status", () => sidecar.status());
  ipcMain.handle("sidecar:load", () => sidecar.loadModel());
  ipcMain.handle("sidecar:settings", () => sidecar.getSettings());
  ipcMain.handle("sidecar:update-settings", async (_event, raw: unknown) => {
    try {
      const settings = SidecarUpdateSettingsSchema.parse(raw);
      return await sidecar.updateSettings(settings);
    } catch (error) {
      throw ipcError("sidecar:update-settings", error);
    }
  });
  ipcMain.handle("sidecar:set-model-path", async (_event, raw: unknown) => {
    try {
      return await sidecar.setModelPath(parseModelPath(raw));
    } catch (error) {
      throw ipcError("sidecar:set-model-path", error);
    }
  });
  ipcMain.handle("sidecar:select-model", async (_event, raw: unknown) => {
    try {
      return await sidecar.selectModel(parseModelPath(raw));
    } catch (error) {
      throw ipcError("sidecar:select-model", error);
    }
  });
  ipcMain.handle("models:list", () => listGgufModels());
}
