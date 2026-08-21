import type { Session } from "@shared/events";
import { shortWorkspace } from "./session";

export type WorkspaceGroup = {
  workspace: string;
  name: string;
  sessions: Session[];
  latestAt: number;
};

export function groupSessionsByWorkspace(
  sessions: Session[],
  search: string,
  activeWorkspace: string,
): WorkspaceGroup[] {
  const q = search.trim().toLowerCase();
  const matched = q
    ? sessions.filter(
        (item) =>
          item.title.toLowerCase().includes(q) ||
          item.workspace.toLowerCase().includes(q) ||
          shortWorkspace(item.workspace).toLowerCase().includes(q),
      )
    : sessions;

  const buckets = new Map<string, Session[]>();
  for (const session of matched) {
    const key = session.workspace || "";
    const list = buckets.get(key) ?? [];
    list.push(session);
    buckets.set(key, list);
  }

  if (activeWorkspace && !buckets.has(activeWorkspace) && !q) {
    buckets.set(activeWorkspace, []);
  }

  const groups: WorkspaceGroup[] = [];
  for (const [workspace, list] of buckets) {
    const sorted = [...list].sort((a, b) => b.updatedAt - a.updatedAt);
    groups.push({
      workspace,
      name: workspace ? shortWorkspace(workspace) : "Unassigned",
      sessions: sorted,
      latestAt: sorted[0]?.updatedAt ?? 0,
    });
  }

  groups.sort((a, b) => b.latestAt - a.latestAt);
  return groups;
}
