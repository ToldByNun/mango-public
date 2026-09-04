import { ipcMain } from "electron";
import { SessionsSaveSchema, ipcError } from "../../shared/ipc-schema";
import type { SessionService } from "../services/session.service";

export function registerSessionIpc(sessions: SessionService): void {
  ipcMain.handle("sessions:list", () => sessions.list());
  ipcMain.handle("sessions:save", (_event, raw: unknown) => {
    try {
      const next = SessionsSaveSchema.parse(raw);
      return sessions.save(next as ReturnType<SessionService["list"]>);
    } catch (error) {
      throw ipcError("sessions:save", error);
    }
  });
}
