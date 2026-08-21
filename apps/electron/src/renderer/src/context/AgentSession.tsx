import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { AgentEvent, Session, TranscriptBlock } from "@shared/events";
import { applyAgentEvent, composeAgentGoal, createSession, newId } from "../lib/session";

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

  const persist = useCallback((next: Session[]) => {
    setSessions(next);
    void api().sessions.save(next);
  }, []);

  const patchActive = useCallback(
    (updater: (session: Session) => Session) => {
      setSessions((prev) => {
        const next = prev.map((item) => (item.id === activeId ? updater(item) : item));
        void api().sessions.save(next);
        return next;
      });
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
    const offEvent = api().agent.onEvent((event: AgentEvent) => {
      if (event.payload?.completion_tokens) {
        setTokens((n) => n + Number(event.payload.completion_tokens));
      }
      if (
        event.event === "agent.started" &&
        typeof event.payload?.workspace === "string" &&
        event.payload.workspace
      ) {
        setWorkspace(event.payload.workspace);
      }
      const persistEvent = event.event !== "agent.token" || event.payload?.done === true;
      setSessions((prev) => {
        const next = prev.map((item) =>
          item.id === event.session_id ? applyAgentEvent(item, event) : item,
        );
        if (persistEvent) void api().sessions.save(next);
        return next;
      });
    });
    const offErr = api().agent.onSidecarError((message) => setSidecarError(message));
    return () => {
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
      const next = sessions.filter((item) => item.id !== id);
      persist(next);
      if (activeId === id) {
        setActiveId(next[0]?.id ?? null);
        setTokens(0);
      }
    },
    [activeId, persist, sessions],
  );

  const send = useCallback(
    async (goal: string, attachments: string[], thinkingLevel: string = "off"): Promise<boolean> => {
      let activeWorkspace = workspace;
      if (!activeWorkspace) {
        const picked = await api().workspace.pick();
        if (!picked) return false;
        activeWorkspace = picked;
        setWorkspace(picked);
        setBranch(await api().workspace.branch().catch(() => "no git"));
      }

      let sessionId = activeId;
      let list = sessions;
      if (!sessionId) {
        const session = createSession(activeWorkspace);
        list = [session, ...sessions];
        persist(list);
        setActiveId(session.id);
        sessionId = session.id;
      }
      const existing = list.find((item) => item.id === sessionId);
      const generateTitle = (existing?.messages.length ?? 0) === 0;
      const userText =
        attachments.length > 0 ? `Files: ${attachments.join(", ")}\n\n${goal}` : goal;
      const priorUsers = (existing?.messages ?? [])
        .filter((item) => item.kind === "user")
        .map((item) => item.text);
      const lastFinal = [...(existing?.messages ?? [])]
        .reverse()
        .find((item) => item.kind === "final" && item.text.trim());
      const runGoal = composeAgentGoal(
        priorUsers,
        userText,
        lastFinal && lastFinal.kind === "final" ? lastFinal.text : "",
      );
      const userBlock: TranscriptBlock = {
        id: newId(),
        kind: "user",
        text: userText,
        createdAt: Date.now(),
      };
      const next = list.map((item) =>
        item.id === sessionId
          ? {
              ...item,
              workspace: activeWorkspace || item.workspace,
              status: "running" as const,
              updatedAt: Date.now(),
              messages: [...item.messages, userBlock],
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
            setSessions((cur) => {
              const patched = cur.map((item) =>
                item.id === sessionId ? { ...item, workspace: autoWorkspace } : item,
              );
              void api().sessions.save(patched);
              return patched;
            });
          }
        })
        .catch((err: unknown) => {
          const message = err instanceof Error ? err.message : String(err);
          setSidecarError(message);
          setSessions((cur) => {
            const patched = cur.map((item) => {
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
            });
            void api().sessions.save(patched);
            return patched;
          });
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
      persist(sessions.map((item) => (item.id === id ? { ...item, title } : item)));
    },
    deleteSession: (id) => {
      const next = sessions.filter((item) => item.id !== id);
      persist(next);
      if (activeId === id) setActiveId(next[0]?.id ?? null);
    },
    deleteWorkspaceSessions: (workspacePath) => {
      const next = sessions.filter((item) => item.workspace !== workspacePath);
      persist(next);
      if (activeId && !next.some((item) => item.id === activeId)) {
        setActiveId(next[0]?.id ?? null);
      }
    },
    pickWorkspace,
    selectWorkspace,
    selectModel,
    send,
    cancel,
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAgent(): Store {
  const value = useContext(Ctx);
  if (!value) throw new Error("useAgent outside provider");
  return value;
}
