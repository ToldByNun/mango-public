import { useEffect, useState } from "react";
import { useAgent } from "../context/AgentSession";
import styles from "../styles/modal.module.css";

export function SettingsModal({ onClose }: { onClose: () => void }): JSX.Element {
  const { selectModel } = useAgent();
  const [modelPath, setModelPath] = useState("");
  const [temperature, setTemperature] = useState("0.1");
  const [topP, setTopP] = useState("0.95");
  const [nCtx, setNCtx] = useState("");
  const [configPath, setConfigPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      setConfigPath(await window.mango.app.configPath());
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
      await window.mango.sidecar.setModelPath(modelPath);
      await selectModel(modelPath);
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
          <span>Settings</span>
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
              Save path
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
