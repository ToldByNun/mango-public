import { BrowserWindow, dialog } from "electron";
import type { AgentEvent } from "../../shared/events";
import { Sidecar } from "../sidecar";

type SendFn = (channel: string, payload: unknown) => void;

export class SidecarService {
  private sidecar: Sidecar | null = null;
  private modelLoaded = false;
  private toolsFingerprint = "";

  constructor(
    private readonly repoRoot: string,
    private readonly runtimeConfig: string,
    private getWorkspace: () => string,
    private send: SendFn,
    private getMainWindow: () => BrowserWindow | null,
  ) {}

  get running(): boolean {
    return Boolean(this.sidecar?.running);
  }

  get isModelLoaded(): boolean {
    return this.modelLoaded;
  }

  status(): { ready: boolean; modelLoaded: boolean } {
    return { ready: Boolean(this.sidecar?.running), modelLoaded: this.modelLoaded };
  }

  setWorkspace(path: string): void {
    this.sidecar?.setWorkspace(path);
  }

  async ensure(): Promise<Sidecar> {
    await this.restartIfStale();
    if (this.sidecar?.running) return this.sidecar;
    this.sidecar = new Sidecar(this.repoRoot, this.getWorkspace() || this.repoRoot, this.runtimeConfig);
    this.sidecar.setEventHandler((event: AgentEvent) => {
      if (event.event === "model.unloaded") {
        this.modelLoaded = false;
      } else if (event.event === "model.loaded") {
        this.modelLoaded = true;
      } else if (event.event === "agent.confirm") {
        void this.handleConfirm(event);
        return;
      }
      this.send("agent:event", event);
    });
    await this.sidecar.start();
    const health = await this.sidecar.request("health", {});
    this.toolsFingerprint = String(health.run_tests_sha256_12 ?? "");
    return this.sidecar;
  }

  async loadModel(): Promise<Record<string, unknown>> {
    const child = await this.ensure();
    const result = await child.request("load_model", {});
    this.modelLoaded = true;
    return result;
  }

  async getSettings(): Promise<Record<string, unknown>> {
    const child = await this.ensure();
    return child.request("get_settings", {});
  }

  async updateSettings(settings: Record<string, unknown>): Promise<Record<string, unknown>> {
    const child = await this.ensure();
    const result = await child.request("update_settings", settings);
    if (settings.reload_model) {
      this.modelLoaded = false;
    }
    return result;
  }

  async setModelPath(modelPath: string): Promise<Record<string, unknown>> {
    const child = await this.ensure();
    const result = await child.request("set_model_path", { path: modelPath });
    this.modelLoaded = false;
    return result;
  }

  async selectModel(modelPath: string): Promise<Record<string, unknown>> {
    const child = await this.ensure();
    await child.request("set_model_path", { path: modelPath });
    await child.stop().catch(() => undefined);
    this.sidecar = null;
    this.modelLoaded = false;
    const next = await this.ensure();
    const result = await next.request("load_model", {});
    this.modelLoaded = true;
    return result;
  }

  async request(method: string, params: Record<string, unknown>, timeoutMs?: number): Promise<Record<string, unknown>> {
    if (!this.sidecar?.running) {
      throw new Error("sidecar not running");
    }
    return this.sidecar.request(method, params, timeoutMs);
  }

  markModelLoaded(): void {
    this.modelLoaded = true;
  }

  async stop(): Promise<void> {
    const child = this.sidecar;
    this.sidecar = null;
    this.modelLoaded = false;
    await child?.stop().catch(() => undefined);
  }

  private async restartIfStale(): Promise<void> {
    if (!this.sidecar?.running) return;
    try {
      const health = await this.sidecar.request("health", {});
      const fp = String(health.run_tests_sha256_12 ?? "");
      if (fp && this.toolsFingerprint && fp !== this.toolsFingerprint) {
        console.warn("[sidecar] run_tests changed; restarting sidecar");
        await this.sidecar.stop();
        this.sidecar = null;
        this.modelLoaded = false;
      } else if (fp) {
        this.toolsFingerprint = fp;
      }
    } catch {
      await this.sidecar.stop().catch(() => undefined);
      this.sidecar = null;
      this.modelLoaded = false;
    }
  }

  private async handleConfirm(event: AgentEvent): Promise<void> {
    const payload = event.payload || {};
    const requestId = String(payload.request_id || "");
    const summary = String(payload.summary || "Allow privileged action?");
    const detail = String(payload.detail || "").trim();
    const kind = String(payload.kind || "shell");
    if (!requestId || !this.sidecar?.running) return;
    const result = await dialog.showMessageBox(this.getMainWindow() ?? undefined, {
      type: "warning",
      buttons: ["Allow", "Deny"],
      defaultId: 1,
      cancelId: 1,
      title: kind === "pip" ? "Install packages?" : "Run command?",
      message: summary,
      detail: detail || undefined,
      noLink: true,
    });
    const allowed = result.response === 0;
    try {
      await this.sidecar.request("confirm", { request_id: requestId, allowed }, 30_000);
    } catch (err) {
      console.error("[sidecar] confirm reply failed", err);
    }
    this.send("agent:event", {
      event: "agent.tool",
      session_id: event.session_id,
      payload: {
        id: `confirm-${requestId}`,
        name: kind === "pip" ? "install_packages" : "run_terminal_command",
        title: allowed ? `Allowed: ${summary}` : `Denied: ${summary}`,
        body: detail || undefined,
        console: true,
        ok: allowed,
        streaming: false,
      },
    });
  }
}
