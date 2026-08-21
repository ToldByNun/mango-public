import { useAgent } from "../context/AgentSession";
import styles from "../styles/shell.module.css";
import { Composer } from "./Composer";
import { DiffModal } from "./DiffModal";
import { IconPlus } from "./Icons";
import { SettingsModal } from "./SettingsModal";
import { Sidebar } from "./Sidebar";
import { Transcript } from "./Transcript";

export function AppShell(): JSX.Element {
  const store = useAgent();

  return (
    <div className={styles.shell}>
      <Sidebar />

      <header className={styles.header}>
        <div className={styles.tabs}>
          {store.active ? (
            <span className={`${styles.tab} ${styles.tabActive}`}>
              <span className={styles.tabName}>{store.active.title}</span>
              <button className={styles.tabClose} type="button" onClick={() => store.closeSession(store.active!.id)}>
                ×
              </button>
            </span>
          ) : null}
        </div>
        <button className={styles.tabNew} type="button" onClick={store.newSession}>
          <IconPlus size={14} />
        </button>
      </header>

      <section className={styles.main}>
        <Transcript />
        <Composer />
      </section>

      {store.diff ? (
        <DiffModal path={store.diff.path} diff={store.diff.diff} onClose={() => store.setDiff(null)} />
      ) : null}
      {store.settingsOpen ? <SettingsModal onClose={() => store.setSettingsOpen(false)} /> : null}
    </div>
  );
}
