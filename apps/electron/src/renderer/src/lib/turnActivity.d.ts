import type { TranscriptBlock } from "@shared/events";
import type { ActivitySegment, DiffLine, TurnActivityStats } from "./turnActivity";

export type {
  ActivitySegment,
  DiffLine,
  ExperimentBlock,
  FileBlock,
  ThoughtBlock,
  ToolBlock,
  TurnActivityStats,
} from "./turnActivity";

export declare function pathLeaf(path: string): string;
export declare function splitTurn(turn: TranscriptBlock[]): {
  user: TranscriptBlock | null;
  activity: TranscriptBlock[];
  finale: TranscriptBlock[];
};
export declare function segmentActivity(blocks: TranscriptBlock[]): ActivitySegment[];
export declare function collectTurnStats(turn: TranscriptBlock[]): TurnActivityStats;
export declare function formatTurnSummary(stats: TurnActivityStats): string | null;
export declare function fileStatusLabel(item: import("./turnActivity").FileBlock): {
  verb: string;
  meta: string;
};
export declare function toolStatusLabel(item: import("./turnActivity").ToolBlock): string;
export declare function experimentStatusMeta(
  item: import("./turnActivity").ExperimentBlock,
): string;
export declare function parseUnifiedDiff(diff: string, limit?: number): DiffLine[];
