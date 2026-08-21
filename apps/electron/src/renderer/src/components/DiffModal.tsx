import { useEffect } from "react";
import styles from "../styles/modal.module.css";

export function DiffModal({
  path,
  diff,
  onClose,
}: {
  path: string;
  diff: string;
  onClose: () => void;
}): JSX.Element {
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className={styles.overlay} onClick={onClose} role="presentation">
      <div className={styles.panel} onClick={(event) => event.stopPropagation()} role="dialog">
        <div className={styles.head}>
          <span>{path}</span>
          <button className={styles.close} type="button" onClick={onClose}>
            ×
          </button>
        </div>
        <div className={styles.body}>
          {diff.split("\n").map((line, index) => {
            const kind = line.startsWith("+") && !line.startsWith("+++")
              ? styles.add
              : line.startsWith("-") && !line.startsWith("---")
                ? styles.del
                : "";
            return (
              <div key={`${index}-${line.slice(0, 24)}`} className={`${styles.line} ${kind}`}>
                {line || " "}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
