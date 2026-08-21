import { useEffect, useMemo, useRef, useState } from "react";
import styles from "../styles/composer.module.css";
import { IconCheck, IconChevron } from "./Icons";
import { ModelBrandIcon } from "./ModelBrandIcon";

type Model = { path: string; label: string };

export function ModelPicker({
  models,
  value,
  disabled,
  onSelect,
}: {
  models: Model[];
  value: string;
  disabled?: boolean;
  onSelect: (path: string) => void;
}): JSX.Element {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);
  const current = models.find((item) => item.path === value);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return models;
    return models.filter((item) => item.label.toLowerCase().includes(q));
  }, [models, query]);

  useEffect(() => {
    if (disabled) setOpen(false);
  }, [disabled]);

  useEffect(() => {
    const onDoc = (event: MouseEvent): void => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  useEffect(() => {
    if (!open) setQuery("");
  }, [open]);

  return (
    <div className={styles.modelPicker} ref={rootRef}>
      <button
        className={styles.modelTrigger}
        type="button"
        disabled={disabled || models.length === 0}
        onClick={() => setOpen((prev) => !prev)}
      >
        <span className={styles.modelBrand}>
          <ModelBrandIcon name={current?.label} path={current?.path ?? value} />
        </span>
        <span className={styles.modelTriggerLabel}>{current?.label ?? "No model"}</span>
        <IconChevron open={open} size={10} />
      </button>
      {open && !disabled && models.length > 0 ? (
        <div className={styles.modelMenu} role="listbox">
          <input
            className={styles.modelSearch}
            placeholder="Search models"
            value={query}
            autoFocus
            onChange={(event) => setQuery(event.target.value)}
          />
          <div className={styles.modelList}>
            {filtered.length === 0 ? (
              <div className={styles.modelEmpty}>No models match</div>
            ) : (
              filtered.map((item) => (
                <button
                  key={item.path}
                  className={`${styles.modelOption} ${item.path === value ? styles.modelOptionActive : ""}`}
                  type="button"
                  role="option"
                  aria-selected={item.path === value}
                  onClick={() => {
                    setOpen(false);
                    if (item.path !== value) onSelect(item.path);
                  }}
                >
                  <span className={styles.modelOptionMain}>
                    <span className={styles.modelBrand}>
                      <ModelBrandIcon name={item.label} path={item.path} />
                    </span>
                    <span className={styles.modelOptionLabel}>{item.label}</span>
                  </span>
                  {item.path === value ? <IconCheck size={12} /> : null}
                </button>
              ))
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
