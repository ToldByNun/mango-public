import type { SidecarService } from "./sidecar.service";
import type { WorkspaceService } from "./workspace.service";
import type { AgentRunInput } from "../../shared/ipc-schema";

export class AgentService {
  constructor(
    private readonly sidecar: SidecarService,
    private readonly workspace: WorkspaceService,
  ) {}

  async run(payload: AgentRunInput): Promise<Record<string, unknown>> {
    const child = await this.sidecar.ensure();
    const ws = this.workspace.resolveAgentWorkspace(payload.sessionId, payload.workspace);
    this.sidecar.setWorkspace(ws);
    const thoughtRaw = payload.thoughtMaxTokens;
    const thoughtMaxTokens =
      typeof thoughtRaw === "number" && Number.isFinite(thoughtRaw)
        ? Math.max(32, Math.min(4096, Math.round(thoughtRaw)))
        : undefined;
    const mode = String(payload.mode || "").trim();
    const result = await child.request("run", {
      session_id: payload.sessionId,
      goal: payload.goal,
      workspace: ws,
      generate_title: Boolean(payload.generateTitle),
      thinking_level: String(payload.thinkingLevel || "off"),
      ...(thoughtMaxTokens != null ? { thought_max_tokens: thoughtMaxTokens } : {}),
      ...(mode ? { mode } : {}),
    });
    this.sidecar.markModelLoaded();
    const used = typeof result.workspace === "string" && result.workspace ? String(result.workspace) : ws;
    this.workspace.adoptIfNeeded(used);
    return { ...result, workspace: used };
  }

  async cancel(sessionId: string): Promise<Record<string, unknown>> {
    if (!this.sidecar.running) return { ok: true };
    return this.sidecar.request("cancel", { session_id: sessionId });
  }

  async continueStall(sessionId: string): Promise<Record<string, unknown>> {
    if (!this.sidecar.running) return { ok: false, continued: false };
    return this.sidecar.request("continue_stall", { session_id: sessionId });
  }

  async undoLastMutation(sessionId: string): Promise<Record<string, unknown>> {
    if (!this.sidecar.running) return { ok: false, error: "sidecar not running" };
    return this.sidecar.request("undo_last_mutation", { session_id: sessionId });
  }
}
