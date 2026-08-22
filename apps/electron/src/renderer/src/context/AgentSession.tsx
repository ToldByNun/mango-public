import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { AgentEvent, Session, TranscriptBlock } from "@shared/events";
import { applyAgentEvent, composeAgentGoal, createSession, newId } from "../lib/session";
import { parseSlashGoal } from "../lib/slashCommands";
import { loadThoughtMaxTokens } from "../lib/thoughtTokens";

function looksLikeQuestionOnly(text: string): boolean {
  const t = text.trim();
  if (!t) return false;
  const asksChange =
    /\b(fix|implement|add|create|write|edit|refactor|debug|rename|delete|remove|baue|schreib|implementier|reparier|ändere|aendere)\b/i.test(
      t,
    );
  if (asksChange) return false;
  if (/^(what|who|where|when|why|how|which|welche[rs]?|was|wie|warum|wieso|wo|wer|erkl[äa]r)\b/i.test(t)) {
    return true;
  }
  return /\?\s*$/.test(t);
}

type MangoApi = typeof window.mango;

type Store = {
  sessions: Session[];
  activeId: string | null;
  workspace: string;
  branch: string;
  modelName: string;
  modelPath: string;
  models: Array<{ path: string; label: string }>;
  modelLoaded: boolean;
  modelSwitching: boolean;
  sidecarError: string | null;
  tokens: number;
  contextMax: number;
  search: string;
  settingsOpen: boolean;
  diff: { path: string; diff: string } | null;
  setSearch: (value: string) => void;
  setSettingsOpen: (open: boolean) => void;
  setDiff: (value: { path: string; diff: string } | null) => void;
  active: Session | null;
  filtered: Session[];
  newSession: () => void;
  selectSession: (id: string) => void;
  closeSession: (id: string) => void;
  renameSession: (id: string, title: string) => void;
  deleteSession: (id: string) => void;
  deleteWorkspaceSessions: (workspace: string) => void;
  pickWorkspace: () => Promise<void>;
  selectWorkspace: (path: string) => Promise<void>;
  selectModel: (path: string) => Promise<void>;
  send: (goal: string, attachments: string[], thinkingLevel?: string) => Promise<boolean>;
  cancel: () => Promise<void>;
  continueStall: () => Promise<void>;
  undoLastMutation: () => Promise<void>;
};

const Ctx = createContext<Store | null>(null);

function api(): MangoApi {
  return window.mango;
}

export function AgentProvider({ children }: { children: ReactNode }): JSX.Element {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [workspace, setWorkspace] = useState("");
  const [branch, setBranch] = useState("no git");
  const [modelName, setModelName] = useState("Local model");
  const [modelPath, setModelPath] = useState("");
  const [models, setModels] = useState<Array<{ path: string; label: string }>>([]);
  const [modelLoaded, setModelLoaded] = useState(false);
  const [modelSwitching, setModelSwitching] = useState(false);
  const [sidecarError, setSidecarError] = useState<string | null>(null);
  const [tokens, setTokens] = useState(0);
  const [contextMax, setContextMax] = useState(16_384);
  const [search, setSearch] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [diff, setDiff] = useState<{ path: string; diff: string } | null>(null);
  const [sessionsLoaded, setSessionsLoaded] = useState(false);
  // Model tokens can arrive faster than React can lay out the transcript. Keep
  // the complete ordered stream, but render it at most once per animation frame.
  const pendingTokenEvents = useRef<AgentEvent[]>([]);
  const tokenFrame = useRef<number | null>(null);
  const pendingSave = useRef(false);

  // Persist sessions exactly once per state change, not inside every updater.
  // This removes the race where multiple async saves could overwrite each other.
  useEffect(() => {
    if (sessionsLoaded && pendingSave.current) {
      pendingSave.current = false;
      void api().sessions.save(sessions);
    }
  }, [sessions, sessionsLoaded]);

  const persist = useCallback((next: Session[]) => {
    pendingSave.current = true;
    setSessions(next);
  }, []);

  const patchActive = useCallback(
    (updater: (session: Session) => Session) => {
      pendingSave.current = true;
      setSessions((prev) => prev.map((item) => (item.id === activeId ? updater(item) : item)));
    },
    [activeId],
  );

  useEffect(() => {
    void (async () => {
      const [listed, ws] = await Promise.all([api().sessions.list(), api().workspace.get()]);
      setSessions(listed);
      setWorkspace(ws);
      if (listed[0]) setActiveId(listed[0].id);
      if (ws) setBranch(await api().workspace.branch());
      setSessionsLoaded(true);
      try {
        const settings = await api().sidecar.settings();
        const path = String(settings.model_path ?? "");
        const name = String(settings.model_name ?? "");
        if (path) setModelPath(path);
        if (name) setModelName(name);
        const nCtx = Number(settings.n_ctx ?? 0);
        if (nCtx > 0) setContextMax(nCtx);
        const listed = await api().models.list();
        const merged = [...listed];
        if (path && !merged.some((item) => item.path === path)) {
          merged.unshift({
            path,
            label: path.split(/[/\\]/).pop()?.replace(/\.gguf$/i, "").replace(/[-_]/g, " ") || "Current model",
          });
        }
        setModels(merged);
      } catch {
        /* sidecar may still be booting */
      }
      const status = await api().sidecar.status().catch(() => ({ ready: false, modelLoaded: false }));
      setModelLoaded(status.modelLoaded);
      if (status.ready) setSidecarError(null);
    })();
    const applyEvents = (events: AgentEvent[]): void => {
      if (events.length === 0) return;
      if (events.some((event) => event.payload?.completion_tokens)) {
        setTokens((n) =>
          n + events.reduce((total, event) => total + Number(event.payload?.completion_tokens ?? 0), 0),
        );
      }
      const started = events.find(
        (event) =>
          event.event === "agent.started" &&
          typeof event.payload?.workspace === "string" &&
          Boolean(event.payload.workspace),
      );
      if (started && typeof started.payload.workspace === "string") {
        setWorkspace(started.payload.workspace);
      }
      const shouldPersist = events.some(
        (event) => event.event !== "agent.token" || event.payload?.done === true,
      );
      if (shouldPersist) pendingSave.current = true;
      setSessions((prev) => {
        const knownIds = new Set(prev.map((item) => item.id));
        let next = prev;
        for (const event of events) {
          if (!knownIds.has(event.session_id)) continue;
          next = next.map((item) =>
            item.id === event.session_id ? applyAgentEvent(item, event) : item,
          );
        }
        return next;
      });
    };
    const flushTokenEvents = (): void => {
      tokenFrame.current = null;
      const events = pendingTokenEvents.current;
      pendingTokenEvents.current = [];
      applyEvents(events);
    };
    const offEvent = api().agent.onEvent((event: AgentEvent) => {
      if (event.event === "agent.token") {
        pendingTokenEvents.current.push(event);
        if (tokenFrame.current === null) {
          tokenFrame.current = window.requestAnimationFrame(flushTokenEvents);
        }
        return;
      }
      // Preserve event order: a tool/final/stopped event must see all preceding
      // token deltas before it updates the same session.
      if (pendingTokenEvents.current.length > 0) {
        if (tokenFrame.current !== null) window.cancelAnimationFrame(tokenFrame.current);
        flushTokenEvents();
      }
      applyEvents([event]);
    });
    const offErr = api().agent.onSidecarError((message) => setSidecarError(message));
    return () => {
      if (tokenFrame.current !== null) window.cancelAnimationFrame(tokenFrame.current);
      tokenFrame.current = null;
      pendingTokenEvents.current = [];
      offEvent();
      offErr();
    };
  }, []);

  const newSession = useCallback(() => {
    const session = createSession(workspace);
    persist([session, ...sessions]);
    setActiveId(session.id);
    setTokens(0);
  }, [persist, sessions, workspace]);

  const selectSession = useCallback(
    (id: string) => {
      setActiveId(id);
      setTokens(0);
      const session = sessions.find((item) => item.id === id);
      if (session?.workspace) {
        setWorkspace(session.workspace);
        void api()
          .workspace.set(session.workspace)
          .then(() => api().workspace.branch())
          .then(setBranch)
          .catch(() => setBranch("no git"));
      }
    },
    [sessions],
  );

  const closeSession = useCallback(
    async (id: string) => {
      const session = sessions.find((item) => item.id === id);
      if (session?.status === "running") {
        try {
          await api().agent.cancel(id);
        } catch (err) {
          setSidecarError(err instanceof Error ? err.message : String(err));
        }
      }
      pendingSave.current = true;
      setSessions((prev) => {
        const next = prev.filter((item) => item.id !== id);
        if (activeId === id) {
          setActiveId(next[0]?.id ?? null);
          setTokens(0);
        }
        return next;
      });
    },
    [activeId, sessions],
  );

  const send = useCallback(
    async (goal: string, attachments: string[], thinkingLevel: string = "off"): Promise<boolean> => {
      const parsed = parseSlashGoal(goal);
      if (parsed.kind === "clear") {
        let sessionId = activeId;
        let list = sessions;
        if (!sessionId) {
          const session = createSession(workspace);
          list = [session, ...sessions];
          persist(list);
          setActiveId(session.id);
          sessionId = session.id;
        }
        const cleared = list.map((item) =>
          item.id === sessionId
            ? {
                ...item,
                messages: [],
                status: "idle" as const,
                updatedAt: Date.now(),
              }
            : item,
        );
        persist(cleared);
        setTokens(0);
        setSidecarError(null);
        return true;
      }

      let activeWorkspace = workspace;
      if (!activeWorkspace) {
        const picked = await api().workspace.pick();
        if (!picked) return false;
        activeWorkspace = picked;
        setWorkspace(picked);
        setBranch(await api().workspace.branch().catch(() => "no git"));
      }

      const mode =
        parsed.kind === "mode"
          ? parsed.mode
          : looksLikeQuestionOnly(parsed.cleanGoal)
            ? "ask"
            : "";
      const cleanGoal = parsed.cleanGoal;
      if (!cleanGoal) return false;

      let sessionId = activeId;
      let list = sessions;
      if (!sessionId) {
        const session = createSession(activeWorkspace);
        if (mode === "plan") {
          session.title = "[Plan] New agent";
        } else if (mode === "ask") {
          session.title = "[Ask] New agent";
        } else if (mode === "debug") {
          session.title = "[Debug] New agent";
        } else if (mode === "refactor") {
          session.title = "[Refactor] New agent";
        }
        list = [session, ...sessions];
        persist(list);
        setActiveId(session.id);
        sessionId = session.id;
      }
      const existing = list.find((item) => item.id === sessionId);
      const generateTitle = (existing?.messages.length ?? 0) === 0;
      const userText =
        attachments.length > 0 ? `Files: ${attachments.join(", ")}\n\n${cleanGoal}` : cleanGoal;
      const priorUsers = (existing?.messages ?? [])
        .filter((item) => item.kind === "user")
        .map((item) => item.text);
      const lastFinal = [...(existing?.messages ?? [])]
        .reverse()
        .find((item) => item.kind === "final" && item.text.trim());
      // Mode prompts must not inherit the "Then edit. Then run_tests..." follow-up suffix.
      const skipCompose = mode === "plan" || mode === "ask" || mode === "refactor" || mode === "debug";
      const runGoal = skipCompose
        ? userText
        : composeAgentGoal(
            priorUsers,
            userText,
            lastFinal && lastFinal.kind === "final" ? lastFinal.text : "",
          );
      const displayText =
        parsed.kind === "mode"
          ? parsed.display
          : mode === "ask"
            ? `/ask ${userText}`
            : userText;
      const userBlock: TranscriptBlock = {
        id: newId(),
        kind: "user",
        text: displayText,
        createdAt: Date.now(),
      };
      const modeTitlePrefix =
        mode === "plan"
          ? "[Plan]"
          : mode === "ask"
            ? "[Ask]"
            : mode === "debug"
              ? "[Debug]"
              : mode === "refactor"
                ? "[Refactor]"
                : "";
      const next = list.map((item) =>
        item.id === sessionId
          ? {
              ...item,
              workspace: activeWorkspace || item.workspace,
              status: "running" as const,
              updatedAt: Date.now(),
              messages: [...item.messages, userBlock],
              ...(generateTitle && modeTitlePrefix
                ? {
                    title: `${modeTitlePrefix} ${cleanGoal.length <= 36 ? cleanGoal : `${cleanGoal.slice(0, 35)}…`}`,
                  }
                : {}),
            }
          : item,
      );
      persist(next);
      setSidecarError(null);
      const runWorkspace =
        activeWorkspace || next.find((item) => item.id === sessionId)?.workspace || "";
      const runPromise = api().agent.run(
        sessionId,
        runGoal,
        runWorkspace,
        generateTitle,
        thinkingLevel,
        loadThoughtMaxTokens(),
        mode || undefined,
      );
      void runPromise
        .then(async (result) => {
          setModelLoaded(true);
          const autoWorkspace =
            typeof result.workspace === "string" && result.workspace
              ? result.workspace
              : activeWorkspace;
          if (autoWorkspace) {
            setWorkspace(autoWorkspace);
            setBranch(await api().workspace.branch().catch(() => "no git"));
            pendingSave.current = true;
            setSessions((cur) =>
              cur.map((item) => (item.id === sessionId ? { ...item, workspace: autoWorkspace } : item)),
            );
          }
        })
        .catch((err: unknown) => {
          const message = err instanceof Error ? err.message : String(err);
          setSidecarError(message);
          pendingSave.current = true;
          setSessions((cur) =>
            cur.map((item) => {
              if (item.id !== sessionId) return item;
              const alreadyErrored = item.messages.some(
                (m) => m.kind === "error" && "text" in m && m.text === message,
              );
              return {
                ...item,
                status: "error" as const,
                messages: alreadyErrored
                  ? item.messages
                  : [
                      ...item.messages,
                      {
                        id: newId(),
                        kind: "error" as const,
                        text: message,
                        createdAt: Date.now(),
                      },
                    ],
              };
            }),
          );
        });
      return true;
    },
    [activeId, persist, sessions, workspace],
  );

  const cancel = useCallback(async () => {
    if (!activeId) return;
    try {
      await api().agent.cancel(activeId);
    } catch (err) {
      setSidecarError(err instanceof Error ? err.message : String(err));
    }
  }, [activeId]);

  const continueStall = useCallback(async () => {
    if (!activeId) return;
    try {
      await api().agent.continueStall(activeId);
    } catch (err) {
      setSidecarError(err instanceof Error ? err.message : String(err));
    }
  }, [activeId]);

  const undoLastMutation = useCallback(async () => {
    if (!activeId) return;
    try {
      await api().agent.undoLastMutation(activeId);
    } catch (err) {
      setSidecarError(err instanceof Error ? err.message : String(err));
    }
  }, [activeId]);

  const selectModel = useCallback(async (path: string) => {
    if (!path || path === modelPath) return;
    setModelSwitching(true);
    setSidecarError(null);
    try {
      await api().sidecar.selectModel(path);
      setModelPath(path);
      const picked = models.find((item) => item.path === path);
      setModelName(picked?.label ?? path.split(/[/\\]/).pop()?.replace(/\.gguf$/i, "") ?? "Local model");
      setModelLoaded(true);
      try {
        const settings = await api().sidecar.settings();
        const nCtx = Number(settings.n_ctx ?? 0);
        if (nCtx > 0) setContextMax(nCtx);
      } catch {
        /* ignore */
      }
    } catch (err) {
      setSidecarError(err instanceof Error ? err.message : String(err));
    } finally {
      setModelSwitching(false);
    }
  }, [modelPath, models]);

  const pickWorkspace = useCallback(async () => {
    const next = await api().workspace.pick();
    setWorkspace(next);
    setBranch(await api().workspace.branch());
    patchActive((session) => ({ ...session, workspace: next }));
  }, [patchActive]);

  const selectWorkspace = useCallback(async (path: string) => {
    if (!path || path === workspace) return;
    await api().workspace.set(path);
    setWorkspace(path);
    setBranch(await api().workspace.branch().catch(() => "no git"));
  }, [workspace]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return sessions;
    return sessions.filter((item) => item.title.toLowerCase().includes(q));
  }, [search, sessions]);

  const active = sessions.find((item) => item.id === activeId) ?? null;

  const value: Store = {
    sessions,
    activeId,
    workspace,
    branch,
    modelName,
    modelPath,
    models,
    modelLoaded,
    modelSwitching,
    sidecarError,
    tokens,
    contextMax,
    search,
    settingsOpen,
    diff,
    setSearch,
    setSettingsOpen,
    setDiff,
    active,
    filtered,
    newSession,
    selectSession,
    closeSession: (id) => {
      void closeSession(id);
    },
    renameSession: (id, title) => {
      pendingSave.current = true;
      setSessions((prev) => prev.map((item) => (item.id === id ? { ...item, title } : item)));
    },
    deleteSession: (id) => {
      pendingSave.current = true;
      setSessions((prev) => {
        const next = prev.filter((item) => item.id !== id);
        if (activeId === id) setActiveId(next[0]?.id ?? null);
        return next;
      });
    },
    deleteWorkspaceSessions: (workspacePath) => {
      pendingSave.current = true;
      setSessions((prev) => {
        const next = prev.filter((item) => item.workspace !== workspacePath);
        if (activeId && !next.some((item) => item.id === activeId)) {
          setActiveId(next[0]?.id ?? null);
        }
        return next;
      });
    },
    pickWorkspace,
    selectWorkspace,
    selectModel,
    send,
    cancel,
    continueStall,
    undoLastMutation,
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAgent(): Store {
  const value = useContext(Ctx);
  if (!value) throw new Error("useAgent outside provider");
  return value;
}
