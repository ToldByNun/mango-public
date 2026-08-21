import type { AgentEvent } from "../shared/events";

export declare class Sidecar {
  constructor(repoRoot: string, workspace: string);
  setEventHandler(handler: ((event: AgentEvent) => void) | null): void;
  get running(): boolean;
  start(): Promise<void>;
  setWorkspace(workspace: string): void;
  request(
    method: string,
    params: Record<string, unknown>,
    timeoutMs?: number,
  ): Promise<Record<string, unknown>>;
  stop(): Promise<void>;
}
