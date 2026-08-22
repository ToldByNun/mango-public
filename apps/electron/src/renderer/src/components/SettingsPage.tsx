import { useEffect, useState } from "react";
import { useAgent } from "../context/AgentSession";
import { loadThinkingLevel, saveThinkingLevel, type ThinkingLevel } from "../lib/thinkingLevel";
import {
  loadThoughtMaxTokens,
  saveThoughtMaxTokens,
  THOUGHT_TOKEN_PRESETS,
} from "../lib/thoughtTokens";
import styles from "../styles/settings.module.css";

type Tab = "model" | "inference" | "hardware" | "agent";

type SettingsState = {
  modelPath: string;
  temperature: string;
  topP: string;
  maxTokens: string;
  nCtx: string;
  nGpuLayers: string;
  nThreads: string;
  gpuBackend: string;
  registeredBackends: string;
  configPath: string;
  thoughtMaxTokens: string;
  thinkingLevel: ThinkingLevel;
};

export function SettingsPage({ onClose }: { onClose: () => void }): JSX.Element {
  const { selectModel } = useAgent();
  const [tab, setTab] = useState<Tab>("model");
  const [models, setModels] = useState<Array<{ path: string; label: string }>>([]);
  const [state, setState] = useState<SettingsState>({
    modelPath: "",
    temperature: "0.1",
    topP: "0.95",
    maxTokens: "2048",
    nCtx: "16384",
    nGpuLayers: "-1",
    nThreads: "0",
    gpuBackend: "",
    registeredBackends: "",
    configPath: "",
    thoughtMaxTokens: "",
    thinkingLevel: loadThinkingLevel(),
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modelDirty, setModelDirty] = useState(false);

  const presetThought = THOUGHT_TOKEN_PRESETS[state.thinkingLevel] ?? 128;

  useEffect(() => {
    void (async () => {
      const configPath = await window.mango.app.configPath();
      const stored = loadThoughtMaxTokens();
      setState((s) => ({
        ...s,
        configPath,
        thoughtMaxTokens: stored == null ? "" : String(stored),
        thinkingLevel: loadThinkingLevel(),
      }));
      try {
        const listed = await window.mango.models.list();
        setModels(listed);
        const settings = await window.mango.sidecar.settings();
        setState((s) => ({
          ...s,
          modelPath: String(settings.model_path ?? ""),
          temperature: String(settings.temperature ?? "0.1"),
          topP: String(settings.top_p ?? "0.95"),
          maxTokens: String(settings.max_tokens ?? "2048"),
          nCtx: String(settings.n_ctx ?? "16384"),
          nGpuLayers: String(settings.n_gpu_layers ?? "-1"),
          nThreads: String(settings.n_threads ?? "0"),
          gpuBackend: String(settings.gpu_backend ?? "cpu"),
          registeredBackends: (settings.registered_backends as string[] | undefined)?.join(", ") ?? "",
          configPath: String(settings.config_path ?? configPath),
        }));
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    })();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const save = async (): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      const rawThought = state.thoughtMaxTokens.trim();
      if (!rawThought) {
        saveThoughtMaxTokens(null);
      } else {
        const n = Number(rawThought);
        if (!Number.isFinite(n) || n < 32 || n > 4096) {
          throw new Error("Thought max tokens must be between 32 and 4096 (or empty for auto).");
        }
        saveThoughtMaxTokens(Math.round(n));
      }
      saveThinkingLevel(state.thinkingLevel);

      const reloadModel =
        tab === "hardware" ||
        tab === "inference" ||
        (tab === "model" && !modelDirty);

      await window.mango.sidecar.updateSettings({
        temperature: Number(state.temperature),
        top_p: Number(state.topP),
        max_tokens: Number(state.maxTokens),
        n_ctx: Number(state.nCtx),
        n_gpu_layers: Number(state.nGpuLayers),
        n_threads: Number(state.nThreads),
        reload_model: reloadModel,
      });

      if (modelDirty && state.modelPath.trim()) {
        await window.mango.sidecar.setModelPath(state.modelPath);
        await selectModel(state.modelPath);
      }
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const set = (patch: Partial<SettingsState>): void => {
    setState((s) => ({ ...s, ...patch }));
  };

  return (
    <div className={styles.overlay} onClick={onClose} role="presentation">
      <div className={styles.panel} onClick={(e) => e.stopPropagation()} role="dialog">
        <header className={styles.header}>
          <h2>Settings</h2>
          <button type="button" className={styles.close} onClick={onClose}>
            ×
          </button>
        </header>
        <nav className={styles.tabs}>
          {(["model", "inference", "hardware", "agent"] as Tab[]).map((id) => (
            <button
              key={id}
              type="button"
              className={tab === id ? styles.tabActive : styles.tab}
              onClick={() => setTab(id)}
            >
              {id.charAt(0).toUpperCase() + id.slice(1)}
            </button>
          ))}
        </nav>
        <div className={styles.body}>
          {tab === "model" ? (
            <section className={styles.section}>
              <label>
                Model path (GGUF)
                <input
                  value={state.modelPath}
                  onChange={(e) => {
                    setModelDirty(true);
                    set({ modelPath: e.target.value });
                  }}
                />
              </label>
              {models.length > 0 ? (
                <label>
                  Detected models
                  <select
                    value={state.modelPath}
                    onChange={(e) => {
                      setModelDirty(true);
                      set({ modelPath: e.target.value });
                    }}
                  >
                    <option value="">— select —</option>
                    {models.map((m) => (
                      <option key={m.path} value={m.path}>
                        {m.label}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
            </section>
          ) : null}
          {tab === "inference" ? (
            <section className={styles.section}>
              <label>
                Temperature
                <input
                  type="number"
                  step="0.05"
                  min="0"
                  max="2"
                  value={state.temperature}
                  onChange={(e) => set({ temperature: e.target.value })}
                />
              </label>
              <label>
                Top P
                <input
                  type="number"
                  step="0.05"
                  min="0"
                  max="1"
                  value={state.topP}
                  onChange={(e) => set({ topP: e.target.value })}
                />
              </label>
              <label>
                Max tokens
                <input
                  type="number"
                  value={state.maxTokens}
                  onChange={(e) => set({ maxTokens: e.target.value })}
                />
              </label>
              <label>
                Context (N_CTX)
                <input type="number" value={state.nCtx} onChange={(e) => set({ nCtx: e.target.value })} />
              </label>
            </section>
          ) : null}
          {tab === "hardware" ? (
            <section className={styles.section}>
              <p className={styles.hint}>
                GPU backend: <strong>{state.gpuBackend || "cpu"}</strong>
                {state.registeredBackends ? ` (${state.registeredBackends})` : null}
              </p>
              <label>
                GPU layers (-1 = all, 0 = CPU only)
                <input
                  type="number"
                  value={state.nGpuLayers}
                  onChange={(e) => set({ nGpuLayers: e.target.value })}
                />
              </label>
              <div className={styles.presets}>
                <button type="button" onClick={() => set({ nGpuLayers: "0" })}>
                  CPU only
                </button>
                <button type="button" onClick={() => set({ nGpuLayers: "-1" })}>
                  GPU all
                </button>
              </div>
              <label>
                CPU threads (0 = auto)
                <input
                  type="number"
                  value={state.nThreads}
                  onChange={(e) => set({ nThreads: e.target.value })}
                />
              </label>
            </section>
          ) : null}
          {tab === "agent" ? (
            <section className={styles.section}>
              <label>
                Thinking level
                <select
                  value={state.thinkingLevel}
                  onChange={(e) => set({ thinkingLevel: e.target.value as ThinkingLevel })}
                >
                  <option value="off">Off</option>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </select>
              </label>
              <label>
                Thought max tokens
                <input
                  value={state.thoughtMaxTokens}
                  onChange={(e) => set({ thoughtMaxTokens: e.target.value })}
                  placeholder={`auto (${presetThought} from ${state.thinkingLevel})`}
                />
              </label>
            </section>
          ) : null}
          <label className={styles.configPath}>
            Config file
            <input value={state.configPath} readOnly />
          </label>
          {error ? <div className={styles.error}>{error}</div> : null}
        </div>
        <footer className={styles.footer}>
          <button type="button" className={styles.ghost} onClick={onClose}>
            Cancel
          </button>
          <button type="button" className={styles.primary} disabled={busy} onClick={() => void save()}>
            Save
          </button>
        </footer>
      </div>
    </div>
  );
}
