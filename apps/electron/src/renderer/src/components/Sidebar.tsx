import { useCallback, useEffect, useMemo, useState, type MouseEvent } from "react";
import type { Session } from "@shared/events";
import { useAgent } from "../context/AgentSession";
import { groupSessionsByWorkspace } from "../lib/workspaceTree";
import { relativeTime } from "../lib/session";
import styles from "../styles/shell.module.css";
import { ContextMenu, type ContextMenuItem } from "./ContextMenu";
import {
  IconChevron,
  IconFilter,
  IconFolder,
  IconPlus,
  IconSearch,
  IconSparkles,
  IconSliders,
  IconZap,
} from "./Icons";

type SessionMenuState = { kind: "session"; x: number; y: number; session: Session };
type FolderMenuState = { kind: "folder"; x: number; y: number; workspace: string; name: string };
type MenuState = SessionMenuState | FolderMenuState;

function sessionLabel(title: string): string {
  const trimmed = title.trim() || "New agent";
  return trimmed.length > 30 ? `${trimmed.slice(0, 29)}…` : trimmed;
}

function SessionRow({
  session,
  active,
  onSelect,
  onContextMenu,
}: {
  session: Session;
  active: boolean;
  onSelect: () => void;
  onContextMenu: (event: MouseEvent) => void;
}): JSX.Element {
  return (
    <button
      className={`${styles.sessionItem} ${active ? styles.sessionItemActive : ""}`}
      type="button"
      onClick={onSelect}
      onContextMenu={onContextMenu}
    >
      <span className={styles.sessionTitle}>{sessionLabel(session.title)}</span>
      <span className={styles.sessionTime}>{relativeTime(session.updatedAt)}</span>
    </button>
  );
}

export function Sidebar(): JSX.Element {
  const store = useAgent();
  const [reposOpen, setReposOpen] = useState(true);
  const [searchOpen, setSearchOpen] = useState(false);
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set());
  const [menu, setMenu] = useState<MenuState | null>(null);

  const groups = useMemo(
    () => groupSessionsByWorkspace(store.sessions, store.search, store.workspace),
    [store.sessions, store.search, store.workspace],
  );

  const toggleFolder = useCallback((workspace: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(workspace)) next.delete(workspace);
      else next.add(workspace);
      return next;
    });
  }, []);

  const openSessionMenu = useCallback((event: MouseEvent, session: Session) => {
    event.preventDefault();
    event.stopPropagation();
    setMenu({ kind: "session", x: event.clientX, y: event.clientY, session });
  }, []);

  const openFolderMenu = useCallback((event: MouseEvent, workspace: string, name: string) => {
    event.preventDefault();
    event.stopPropagation();
    setMenu({ kind: "folder", x: event.clientX, y: event.clientY, workspace, name });
  }, []);

  const sessionMenuItems = useCallback(
    (session: Session): ContextMenuItem[] => [
      {
        id: "rename",
        label: "Rename",
        onSelect: () => {
          const title = window.prompt("Rename agent", session.title);
          if (title?.trim()) store.renameSession(session.id, title.trim());
        },
      },
      {
        id: "open",
        label: "Open Workspace Folder",
        onSelect: () => {
          if (session.workspace) void window.mango.app.openPath(session.workspace);
        },
      },
      {
        id: "delete",
        label: "Delete",
        danger: true,
        onSelect: () => store.deleteSession(session.id),
      },
    ],
    [store],
  );

  const folderMenuItems = useCallback(
    (workspace: string, name: string): ContextMenuItem[] => [
      {
        id: "open",
        label: "Open Workspace Folder",
        onSelect: () => {
          if (workspace) void window.mango.app.openPath(workspace);
        },
      },
      {
        id: "delete-all",
        label: "Delete All Agents",
        danger: true,
        onSelect: () => {
          const count = store.sessions.filter((item) => item.workspace === workspace).length;
          if (count === 0) return;
          const label = name || "this folder";
          if (window.confirm(`Delete all ${count} agent${count === 1 ? "" : "s"} in ${label}?`)) {
            store.deleteWorkspaceSessions(workspace);
          }
        },
      },
    ],
    [store],
  );

  const activeMenuItems = useMemo((): ContextMenuItem[] => {
    if (!menu) return [];
    if (menu.kind === "session") return sessionMenuItems(menu.session);
    return folderMenuItems(menu.workspace, menu.name);
  }, [folderMenuItems, menu, sessionMenuItems]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const mod = event.metaKey || event.ctrlKey;
      if (!mod) return;
      if (event.key.toLowerCase() === "n") {
        event.preventDefault();
        store.newSession();
      }
      if (event.key.toLowerCase() === "f") {
        event.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [store]);

  return (
    <aside className={styles.sidebar}>
      <div className={styles.sideTop}>
        <button className={styles.sideAction} type="button" onClick={() => store.newSession()}>
          <IconSparkles size={14} />
          <span>New Agent</span>
          <kbd className={styles.kbd}>⌘N</kbd>
        </button>
        <button
          className={`${styles.sideAction} ${searchOpen ? styles.sideActionActive : ""}`}
          type="button"
          onClick={() => setSearchOpen((open) => !open)}
        >
          <IconSearch size={14} />
          <span>Search</span>
          <kbd className={styles.kbd}>⌘F</kbd>
        </button>
        <button className={styles.sideActionMuted} type="button" onClick={() => store.setSettingsOpen(true)}>
          <IconSliders size={14} />
          <span>Customize</span>
        </button>
      </div>

      {searchOpen ? (
        <input
          className={styles.search}
          autoFocus
          placeholder="Filter agents across repositories…"
          value={store.search}
          onChange={(event) => store.setSearch(event.target.value)}
        />
      ) : null}

      <div className={styles.repoSection}>
        <div className={styles.repoHeader}>
          <button className={styles.repoHeaderToggle} type="button" onClick={() => setReposOpen((o) => !o)}>
            <IconChevron open={reposOpen} />
            <span className={styles.repoHeaderLabel}>Repositories</span>
          </button>
          <span className={styles.repoHeaderActions}>
            <button className={styles.iconGhost} type="button" title="Filter agents" onClick={() => setSearchOpen(true)}>
              <IconFilter size={13} />
            </button>
            <button className={styles.iconGhost} type="button" title="New repository" onClick={() => void store.pickWorkspace()}>
              <IconPlus size={13} />
            </button>
          </span>
        </div>

        {reposOpen ? (
          <div className={styles.repoTree}>
            {groups.length === 0 ? (
              <div className={styles.emptyRepo}>No repositories yet</div>
            ) : (
              groups.map((group) => {
                const open = !collapsed.has(group.workspace);
                const isActiveWorkspace = store.workspace === group.workspace;
                const sessions = [...group.sessions].sort((a, b) => b.updatedAt - a.updatedAt);
                return (
                  <div key={group.workspace || "__none__"} className={styles.folderBlock}>
                    <button
                      className={`${styles.folderRow} ${isActiveWorkspace ? styles.folderRowActive : ""}`}
                      type="button"
                      onClick={() => {
                        toggleFolder(group.workspace);
                        if (group.workspace) void store.selectWorkspace(group.workspace);
                      }}
                      onContextMenu={(event) => openFolderMenu(event, group.workspace, group.name)}
                    >
                      <span className={styles.chevronSlot}>
                        <IconChevron open={open} size={12} />
                      </span>
                      <span className={styles.folderIcon}>
                        <IconFolder size={16} />
                      </span>
                      <span className={styles.folderName}>{group.name}</span>
                      <span className={styles.folderCount}>{group.sessions.length || ""}</span>
                    </button>
                    {open ? (
                      <div className={styles.sessionNest}>
                        {sessions.length === 0 ? (
                          <div className={styles.emptyAgents}>No agents yet</div>
                        ) : (
                          sessions.map((item) => (
                            <SessionRow
                              key={item.id}
                              session={item}
                              active={item.id === store.activeId}
                              onSelect={() => {
                                store.selectSession(item.id);
                                if (item.workspace) void store.selectWorkspace(item.workspace);
                              }}
                              onContextMenu={(event) => openSessionMenu(event, item)}
                            />
                          ))
                        )}
                      </div>
                    ) : null}
                  </div>
                );
              })
            )}
          </div>
        ) : null}
      </div>

      <GitHubAccount />

      {menu ? (
        <ContextMenu x={menu.x} y={menu.y} items={activeMenuItems} onClose={() => setMenu(null)} />
      ) : null}
    </aside>
  );
}

function GitHubAccount(): JSX.Element {
  const [state, setState] = useState<{ loggedIn: boolean; user?: { login: string; avatar_url: string; name: string | null } }>({ loggedIn: false });
  const [loading, setLoading] = useState(false);
  const [deviceCode, setDeviceCode] = useState<string | null>(null);

  useEffect(() => {
    void window.mango.github.status().then(setState);
    const unsub = window.mango.github.onDeviceCode(({ userCode }) => {
      setDeviceCode(userCode);
    });
    return unsub;
  }, []);

  const login = async (): Promise<void> => {
    setLoading(true);
    setDeviceCode(null);
    try {
      const result = await window.mango.github.login();
      setState(result);
    } catch {
      setState({ loggedIn: false });
    }
    setLoading(false);
    setDeviceCode(null);
  };

  const logout = async (): Promise<void> => {
    await window.mango.github.logout();
    setState({ loggedIn: false });
  };

  if (state.loggedIn && state.user) {
    return (
      <div className={styles.sideBottom}>
        <div className={styles.accountCard}>
          <img src={state.user.avatar_url} width={20} height={20} className={styles.accountAvatar} alt="" />
          <span className={styles.accountName}>{state.user.login}</span>
          <button className={styles.accountLogout} type="button" onClick={() => void logout()} title="Sign out">
            ×
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.sideBottom}>
      {deviceCode ? (
        <div className={styles.deviceCode}>
          <span className={styles.deviceCodeLabel}>Enter code on GitHub:</span>
          <code className={styles.deviceCodeValue}>{deviceCode}</code>
        </div>
      ) : (
        <button className={styles.accountBtn} type="button" disabled={loading} onClick={() => void login()}>
          <svg width={14} height={14} viewBox="0 0 16 16" fill="currentColor">
            <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
          </svg>
          <span>{loading ? "Waiting…" : "Sign in with GitHub"}</span>
        </button>
      )}
    </div>
  );
}
