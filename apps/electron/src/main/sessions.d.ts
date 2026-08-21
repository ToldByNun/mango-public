import type { Session } from "../shared/events";
export declare function loadSessions(filePath: string): Session[];
export declare function saveSessions(filePath: string, sessions: Session[]): void;
