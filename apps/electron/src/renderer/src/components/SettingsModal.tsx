import { useEffect, useState } from "react";
import { useAgent } from "../context/AgentSession";
import { loadThinkingLevel } from "../lib/thinkingLevel";
import {
  loadThoughtMaxTokens,
  saveThoughtMaxTokens,
  THOUGHT_TOKEN_PRESETS,
} from "../lib/thoughtTokens";
import styles from "../styles/modal.module.css";

export function SettingsModal({ onClose }: { onClose: () => void }): JSX.Element {
  const { selectModel } = useAgent();
  const [modelPath, setModelPath] = useState("");
  const [temperature, setTemperature] = useState("0.1");
  const [topP, setTopP] = useState("0.95");
  const [nCtx, setNCtx] = useState("");
  const [configPath, setConfigPath] = useState("");
  const [thoughtMaxTokens, setThoughtMaxTokens] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const thinkingLevel = loadThinkingLevel();
  const presetThought = THOUGHT_TOKEN_PRESETS[thinkingLevel] ?? 128;

  useEffect(() => {
    void (async () => {
      setConfigPath(await window.mango.app.configPath());
      const stored = loadThoughtMaxTokens();
      setThoughtMaxTokens(stored == null ? "" : String(stored));
      try {
        const settings = await window.mango.sidecar.settings();
        setModelPath(String(settings.model_path ?? ""));
        setTemperature(String(settings.temperature ?? "0.1"));
        setTopP(String(settings.top_p ?? "0.95"));
        setNCtx(String(settings.n_ctx ?? ""));
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
      const raw = thoughtMaxTokens.trim();
      if (!raw) {
        saveThoughtMaxTokens(null);
      } else {
        const n = Number(raw);
        if (!Number.isFinite(n) || n < 32 || n > 4096) {
          throw new Error("Thought max tokens must be between 32 and 4096 (or empty for auto).");
        }
        saveThoughtMaxTokens(Math.round(n));
      }
      if (modelPath.trim()) {
        await window.mango.sidecar.setModelPath(modelPath);
        await selectModel(modelPath);
      }
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={styles.overlay} onClick={onClose} role="presentation">
      <div className={styles.panel} onClick={(event) => event.stopPropagation()} role="dialog">
        <div className={styles.head}>
          <span>Customize</span>
          <button className={styles.close} type="button" onClick={onClose}>
            ×
          </button>
        </div>
        <div className={styles.form}>
          <label>
            MODEL PATH
            <input value={modelPath} onChange={(event) => setModelPath(event.target.value)} />
          </label>
          <label>
            THOUGHT MAX TOKENS
            <input
              value={thoughtMaxTokens}
              onChange={(event) => setThoughtMaxTokens(event.target.value)}
              placeholder={`auto (${presetThought} from Thinking · ${thinkingLevel})`}
              inputMode="numeric"
            />
          </label>
          <label>
            TEMPERATURE
            <input value={temperature} readOnly />
          </label>
          <label>
            TOP P
            <input value={topP} readOnly />
          </label>
          <label>
            N_CTX
            <input value={nCtx} readOnly />
          </label>
          <label>
            CONFIG
            <input value={configPath} readOnly />
          </label>
          {error ? <div style={{ color: "var(--danger)", fontSize: 12 }}>{error}</div> : null}
          <div className={styles.actions}>
            <button className={styles.ghost} type="button" onClick={onClose}>
              Cancel
            </button>
            <button className={styles.primary} type="button" disabled={busy} onClick={() => void save()}>
              Save
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
