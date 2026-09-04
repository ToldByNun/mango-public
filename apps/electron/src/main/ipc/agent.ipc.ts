import { ipcMain } from "electron";
import { AgentRunSchema, SessionIdSchema, ipcError } from "../../shared/ipc-schema";
import type { AgentService } from "../services/agent.service";

export function registerAgentIpc(agent: AgentService): void {
  ipcMain.handle("agent:run", async (_event, raw: unknown) => {
    try {
      const payload = AgentRunSchema.parse(raw);
      return await agent.run(payload);
    } catch (error) {
      throw ipcError("agent:run", error);
    }
  });
  ipcMain.handle("agent:cancel", async (_event, raw: unknown) => {
    try {
      const sessionId = SessionIdSchema.parse(raw);
      return await agent.cancel(sessionId);
    } catch (error) {
      throw ipcError("agent:cancel", error);
    }
  });
  ipcMain.handle("agent:continueStall", async (_event, raw: unknown) => {
    try {
      const sessionId = SessionIdSchema.parse(raw);
      return await agent.continueStall(sessionId);
    } catch (error) {
      throw ipcError("agent:continueStall", error);
    }
  });
  ipcMain.handle("agent:undoLastMutation", async (_event, raw: unknown) => {
    try {
      const sessionId = SessionIdSchema.parse(raw);
      return await agent.undoLastMutation(sessionId);
    } catch (error) {
      throw ipcError("agent:undoLastMutation", error);
    }
  });
}
