import { ChildProcessWithoutNullStreams, spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { promptsDir, pythonExecutable, runtimeConfigPath } from "./paths";
import type { AgentEvent } from "../shared/events";

type Pending = {
  resolve: (value: Record<string, unknown>) => void;
  reject: (error: Error) => void;
  timer?: ReturnType<typeof setTimeout>;
};

const DEFAULT_RPC_TIMEOUT_MS = 120_000;

export class Sidecar {
  private child: ChildProcessWithoutNullStreams | null = null;
  private pending = new Map<string, Pending>();
  private seq = 0;
  private onEvent: ((event: AgentEvent) => void) | null = null;
  private activeRunSessionId: string | null = null;
  private stderrTail = "";

  constructor(
    private repoRoot: string,
    private workspace: string,
  ) {}

  setEventHandler(handler: ((event: AgentEvent) => void) | null): void {
    this.onEvent = handler;
  }

  get running(): boolean {
    return this.child !== null && this.child.exitCode === null;
  }

  async start(): Promise<void> {
    if (this.running) return;
    const python = pythonExecutable(this.repoRoot);
    const config = runtimeConfigPath(this.repoRoot);
    this.stderrTail = "";
    this.child = spawn(
      python,
      ["-u", "-m", "mango_agent.serve", "--config", config],
      {
        cwd: this.repoRoot,
        windowsHide: true,
        env: {
          ...process.env,
          PYTHONUNBUFFERED: "1",
          PYTHONNOUSERSITE: "1",
          GGML_CUDA_DISABLE_GRAPHS: "1",
          GGML_CUDA_ENABLE_GRAPHS: "0",
          MANGO_PROMPTS_DIR: promptsDir(this.repoRoot),
        },
        stdio: ["pipe", "pipe", "pipe"],
      },
    );
    const child = this.child;
    child.on("error", (err) => {
      console.error("[sidecar] spawn error", err);
      const detail = err instanceof Error ? err.message : String(err);
      this.failPending(new Error(`sidecar spawn failed (${python}): ${detail}`));
      this.child = null;
    });
    child.stderr.on("data", (chunk: Buffer) => {
      const text = chunk.toString("utf8");
      if (text.trim()) console.error("[sidecar]", text.trim());
      this.stderrTail = `${this.stderrTail}${text}`.slice(-4000);
    });
    child.on("exit", (code) => {
      this.child = null;
      const tip = this.stderrTail.trim().replace(/\s+/g, " ").slice(-500);
      const message = tip
        ? `sidecar exited (${code ?? "null"}): ${tip}`
        : `sidecar exited (${code ?? "null"}) — python=${python}`;
      this.failPending(new Error(message));
      if (this.activeRunSessionId) {
        const sessionId = this.activeRunSessionId;
        this.activeRunSessionId = null;
        this.onEvent?.({
          event: "agent.error",
          session_id: sessionId,
          payload: { text: message },
        });
        this.onEvent?.({
          event: "agent.stopped",
          session_id: sessionId,
          payload: { reason: "error", error: message },
        });
      }
    });
    const rl = createInterface({ input: child.stdout });
    rl.on("line", (line) => this.handleLine(line));
    await this.request("health", {}, 30_000);
  }

  setWorkspace(workspace: string): void {
    this.workspace = workspace;
  }

  async request(
    method: string,
    params: Record<string, unknown>,
    timeoutMs: number = DEFAULT_RPC_TIMEOUT_MS,
  ): Promise<Record<string, unknown>> {
    if (!this.child) throw new Error("sidecar is not running");
    this.seq += 1;
    const id = String(this.seq);
    if (method === "run") {
      this.activeRunSessionId = String(params.session_id ?? "") || null;
    }
    if (method === "shutdown") {
      this.activeRunSessionId = null;
    }
    // Streaming / long-running RPCs: no client timeout (cancel or process exit ends them).
    const effectiveTimeout =
      method === "run" || method === "cancel" ? 0 : timeoutMs;
    const payload = JSON.stringify({ id, method, params });
    return new Promise((resolve, reject) => {
      const timer =
        effectiveTimeout > 0
          ? setTimeout(() => {
              if (!this.pending.has(id)) return;
              this.pending.delete(id);
              reject(new Error(`sidecar timeout (${method}, ${effectiveTimeout}ms)`));
            }, effectiveTimeout)
          : undefined;
      this.pending.set(id, {
        resolve: (value) => {
          if (timer) clearTimeout(timer);
          resolve(value);
        },
        reject: (error) => {
          if (timer) clearTimeout(timer);
          reject(error);
        },
        timer,
      });
      this.child!.stdin.write(`${payload}\n`, (err) => {
        if (err) {
          const wait = this.pending.get(id);
          if (wait?.timer) clearTimeout(wait.timer);
          this.pending.delete(id);
          reject(err);
        }
      });
    });
  }

  async stop(): Promise<void> {
    if (!this.child) return;
    const child = this.child;
    const pid = child.pid;
    const exited = new Promise<void>((resolve) => {
      if (child.exitCode !== null) {
        resolve();
        return;
      }
      child.once("exit", () => resolve());
    });
    try {
      // Ask the Python side to cancel the run, neutralize CUDA, and exit.
      await this.request("shutdown", {}, 3_000);
    } catch {
      /* ignore — process may already be exiting */
    }
    // Large models need time to cancel the decode and finish sys.exit teardown.
    await Promise.race([exited, new Promise<void>((resolve) => setTimeout(resolve, 15_000))]);
    if (child.exitCode === null) {
      try {
        child.kill();
      } catch {
        /* ignore */
      }
    }
    if (child.exitCode === null && pid && process.platform === "win32") {
      try {
        spawn("taskkill", ["/F", "/T", "/PID", String(pid)], {
          windowsHide: true,
          stdio: "ignore",
        });
      } catch {
        /* ignore */
      }
      await Promise.race([exited, new Promise<void>((resolve) => setTimeout(resolve, 3_000))]);
    }
    this.child = null;
    this.activeRunSessionId = null;
  }

  private failPending(error: Error): void {
    for (const [, wait] of this.pending) {
      if (wait.timer) clearTimeout(wait.timer);
      wait.reject(error);
    }
    this.pending.clear();
  }

  private handleLine(line: string): void {
    const trimmed = line.trim();
    if (!trimmed) return;
    let message: Record<string, unknown>;
    try {
      message = JSON.parse(trimmed) as Record<string, unknown>;
    } catch {
      console.error("[sidecar] bad json", trimmed.slice(0, 200));
      return;
    }
    if (typeof message.event === "string") {
      if (message.event === "agent.stopped") this.activeRunSessionId = null;
      this.onEvent?.(message as AgentEvent);
      return;
    }
    const id = String(message.id ?? "");
    const wait = this.pending.get(id);
    if (!wait) return;
    this.pending.delete(id);
    if (wait.timer) clearTimeout(wait.timer);
    if (message.ok === false) {
      wait.reject(new Error(String(message.error ?? "sidecar error")));
      return;
    }
    wait.resolve((message.result as Record<string, unknown>) ?? {});
  }
}
