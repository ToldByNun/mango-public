import type { AgentEvent, Session, TranscriptBlock } from "@shared/events";
export declare function newId(): string;
export declare function composeAgentGoal(
  priorUserMessages: string[],
  latest: string,
  lastSummary?: string,
): string;
export declare function titleFromGoal(goal: string): string;
export declare function relativeTime(ts: number, now?: number): string;
export declare function shortPath(path: string): string;
export declare function shortWorkspace(path: string): string;
export declare function applyAgentEvent(session: Session, event: AgentEvent): Session;
export declare function actionSummary(messages: TranscriptBlock[]): {
    edited: number;
    read: number;
    verify?: "pass" | "fail";
};
export declare function createSession(workspace: string, title?: string): Session;
