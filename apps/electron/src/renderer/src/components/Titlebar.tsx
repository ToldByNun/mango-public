import { useAgent } from "../context/AgentSession";
import { useState, useRef, useEffect } from "react";
import styles from "../styles/titlebar.module.css";
import mangoLogo from "../assets/mango-logo.png";

const menus: Record<string, string[]> = {
  File: ["New Agent", "---", "Exit"],
  Help: ["Check for Updates", "About Mango"],
};

export function Titlebar() {
  const { newSession } = useAgent();
  const [open, setOpen] = useState<string | null>(null);
  const barRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (barRef.current && !barRef.current.contains(e.target as Node)) setOpen(null);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleAction = (label: string) => {
    const cmd = label.split("  ")[0];
    switch (cmd) {
      case "New Agent":
        newSession();
        break;
      case "Exit":
        window.mango.win.close();
        break;
      case "Check for Updates":
        void window.mango.app.checkUpdates();
        break;
      case "About Mango":
        void (async () => {
          const version = await window.mango.app.version();
          window.alert(`Mango ${version}\nLocal coding agent`);
        })();
        break;
      default:
        break;
    }
  };

  return (
    <div className={styles.titlebar} ref={barRef}>
      <div className={styles.icon}><img src={mangoLogo} alt="Mango" width={16} height={16} /></div>
      <div className={styles.menus}>
        {Object.keys(menus).map((label) => (
          <div key={label} className={styles.menuItem}>
            <button
              className={`${styles.menuBtn} ${open === label ? styles.menuBtnActive : ""}`}
              onMouseDown={() => setOpen(open === label ? null : label)}
              onMouseEnter={() => open && setOpen(label)}
            >
              {label}
            </button>
            {open === label && (
              <div className={styles.dropdown}>
                {menus[label].map((item, i) =>
                  item === "---" ? (
                    <div key={i} className={styles.sep} />
                  ) : (
                    <button key={i} className={styles.dropItem} onClick={() => { setOpen(null); handleAction(item); }}>
                      <span>{item.split("  ")[0]}</span>
                      {item.includes("  ") && <span className={styles.shortcut}>{item.split("  ")[1]}</span>}
                    </button>
                  ),
                )}
              </div>
            )}
          </div>
        ))}
      </div>
      <div className={styles.drag} />
      <div className={styles.controls}>
        <button className={styles.ctrlBtn} onClick={() => window.mango.win.minimize()} aria-label="Minimize">
          <svg width="10" height="1" viewBox="0 0 10 1"><rect width="10" height="1" fill="currentColor" /></svg>
        </button>
        <button className={styles.ctrlBtn} onClick={() => window.mango.win.maximize()} aria-label="Maximize">
          <svg width="10" height="10" viewBox="0 0 10 10"><rect x="0.5" y="0.5" width="9" height="9" fill="none" stroke="currentColor" strokeWidth="1" /></svg>
        </button>
        <button className={`${styles.ctrlBtn} ${styles.ctrlClose}`} onClick={() => window.mango.win.close()} aria-label="Close">
          <svg width="10" height="10" viewBox="0 0 10 10"><path d="M0 0L10 10M10 0L0 10" stroke="currentColor" strokeWidth="1.2" /></svg>
        </button>
      </div>
    </div>
  );
}
