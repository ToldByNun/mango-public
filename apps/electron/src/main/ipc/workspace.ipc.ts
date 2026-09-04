import { dialog, ipcMain } from "electron";
import { PathStringSchema, WorkspaceSetSchema, ipcError } from "../../shared/ipc-schema";
import type { WorkspaceService } from "../services/workspace.service";

export function registerWorkspaceIpc(workspace: WorkspaceService): void {
  ipcMain.handle("workspace:get", () => workspace.get());
  ipcMain.handle("workspace:pick", () => workspace.pick());
  ipcMain.handle("workspace:branch", () => workspace.branch());
  ipcMain.handle("workspace:set", (_event, raw: unknown) => {
    try {
      const path =
        typeof raw === "string"
          ? PathStringSchema.parse(raw)
          : WorkspaceSetSchema.parse(raw).path;
      return workspace.set(path);
    } catch (error) {
      throw ipcError("workspace:set", error);
    }
  });
  ipcMain.handle("files:pick", async () => {
    const result = await dialog.showOpenDialog({
      title: "Attach files",
      defaultPath: workspace.get() || undefined,
      properties: ["openFile", "multiSelections"],
    });
    return result.canceled ? [] : result.filePaths;
  });
}
