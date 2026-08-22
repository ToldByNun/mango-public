import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useAgent } from "../context/AgentSession";
import { useSpeechInput } from "../lib/useSpeechInput";
import { shortWorkspace } from "../lib/session";
import styles from "../styles/composer.module.css";
import {
  loadThinkingLevel,
  saveThinkingLevel,
  THINKING_OPTIONS,
  type ThinkingLevel,
} from "../lib/thinkingLevel";
import { ContextRing, IconArrowUp, IconGitBranch, IconMic, IconMonitor, IconPlus, IconStop, IconThink, IconUndo } from "./Icons";
import { ModelPicker } from "./ModelPicker";

export function Composer(): JSX.Element {
  const {
    active,
    branch,
    models,
    modelPath,
    modelSwitching,
    selectModel,
    send,
    cancel,
    continueStall,
    undoLastMutation,
    sidecarError,
    workspace,
    pickWorkspace,
    tokens,
    contextMax,
  } = useAgent();
  const [text, setText] = useState("");
  const [files, setFiles] = useState<string[]>([]);
  const [thinkingLevel, setThinkingLevel] = useState<ThinkingLevel>(() => loadThinkingLevel());
  const [speechError, setSpeechError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);
  const running = active?.status === "running";

  const attachFiles = async (): Promise<void> => {
    const picked = await window.mango.files.pick();
    if (picked.length) setFiles((prev) => [...prev, ...picked.filter((p) => !prev.includes(p))]);
  };

  useEffect(() => {
    let dragCount = 0;
    const onDragEnter = (e: DragEvent): void => {
      e.preventDefault();
      dragCount++;
      if (e.dataTransfer?.types.includes("Files")) setDragOver(true);
    };
    const onDragLeave = (e: DragEvent): void => {
      e.preventDefault();
      dragCount--;
      if (dragCount <= 0) { dragCount = 0; setDragOver(false); }
    };
    const onDragOver = (e: DragEvent): void => { e.preventDefault(); if (e.dataTransfer) e.dataTransfer.dropEffect = "copy"; };
    const onDrop = (e: DragEvent): void => {
      e.preventDefault();
      dragCount = 0;
      setDragOver(false);
      const dropped: string[] = [];
      if (e.dataTransfer?.files) {
        for (let i = 0; i < e.dataTransfer.files.length; i++) {
          const f = e.dataTransfer.files[i];
          const p = window.mango.getPathForFile(f);
          if (p) dropped.push(p);
        }
      }
      if (dropped.length) setFiles((prev) => [...prev, ...dropped.filter((p) => !prev.includes(p))]);
    };
    document.addEventListener("dragenter", onDragEnter);
    document.addEventListener("dragleave", onDragLeave);
    document.addEventListener("dragover", onDragOver);
    document.addEventListener("drop", onDrop);
    return () => {
      document.removeEventListener("dragenter", onDragEnter);
      document.removeEventListener("dragleave", onDragLeave);
      document.removeEventListener("dragover", onDragOver);
      document.removeEventListener("drop", onDrop);
    };
  }, []);

  const appendSpeech = useCallback((chunk: string) => {
    setSpeechError(null);
    setText((prev) => {
      const spacer = prev && !prev.endsWith(" ") ? " " : "";
      return `${prev}${spacer}${chunk.trim()}`;
    });
  }, []);

  const speech = useSpeechInput(appendSpeech, setSpeechError);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(140, el.scrollHeight)}px`;
  }, [text]);

  const onKey = (event: KeyboardEvent<HTMLTextAreaElement>): void => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  };

  const submit = async (): Promise<void> => {
    const goal = text.trim();
    if (!goal || running) return;
    const attached = files;
    const started = await send(goal, attached, thinkingLevel);
    if (started) {
      setText("");
      setFiles([]);
    }
  };

  return (
    <div className={styles.dock}>
      {sidecarError ? <div className={styles.hintError}>{sidecarError}</div> : null}
      {speechError ? <div className={styles.hintError}>{speechError}</div> : null}
      {!workspace ? (
        <div className={styles.hint}>No workspace selected — pick a folder before the agent runs.</div>
      ) : null}
      <div className={`${styles.shell} ${dragOver ? styles.shellDragOver : ""}`}>
        {dragOver ? <div className={styles.dropOverlay}>Drop files to attach</div> : null}
        {files.length > 0 ? (
          <div className={styles.chips}>
            {files.map((path) => {
              const name = path.split(/[/\\]/).pop() || path;
              const ext = name.includes(".") ? name.split(".").pop()?.toUpperCase() : "FILE";
              return (
                <span key={path} className={styles.chip}>
                  <span className={styles.chipExt}>{ext}</span>
                  <span className={styles.chipName}>{name}</span>
                  <button type="button" onClick={() => setFiles(files.filter((item) => item !== path))}>
                    ×
                  </button>
                </span>
              );
            })}
          </div>
        ) : null}
        <div className={styles.inputWrap}>
          <textarea
            ref={ref}
            className={styles.input}
            value={text}
            disabled={running}
            placeholder="Ask Mango to build, fix, or explain…"
            onChange={(event) => setText(event.target.value)}
            onKeyDown={onKey}
            rows={1}
          />
        </div>
        <div className={styles.toolbar}>
          <div className={styles.toolbarLeft}>
            <button
              className={styles.iconBtn}
              type="button"
              title="Attach files"
              disabled={running}
              onClick={() => void attachFiles()}
            >
              <IconPlus size={15} />
            </button>
            <ThinkingPicker
              value={thinkingLevel}
              disabled={running}
              onChange={(level) => {
                setThinkingLevel(level);
                saveThinkingLevel(level);
              }}
            />
            <ModelPicker
              models={models}
              value={modelPath}
              disabled={running || modelSwitching}
              onSelect={(path) => void selectModel(path)}
            />
          </div>
          <div className={styles.toolbarRight}>
            <button
              className={`${styles.iconBtn} ${speech.listening ? styles.iconBtnActive : ""}`}
              type="button"
              title={speech.listening ? "Stop listening" : "Voice input"}
              disabled={running}
              onClick={speech.toggle}
            >
              <IconMic size={15} />
            </button>
            {running ? (
              <>
                <button
                  className={styles.iconBtn}
                  type="button"
                  title="Undo last file change"
                  onClick={() => void undoLastMutation()}
                >
                  <IconUndo size={15} />
                </button>
                <button
                  className={styles.iconBtn}
                  type="button"
                  title="Continue after stall"
                  onClick={() => void continueStall()}
                >
                  Go
                </button>
                <button className={`${styles.send} ${styles.stop}`} type="button" onClick={() => void cancel()}>
                  <IconStop />
                </button>
              </>
            ) : (
              <button className={styles.send} type="button" disabled={!text.trim()} onClick={() => void submit()}>
                <IconArrowUp size={14} />
              </button>
            )}
          </div>
        </div>
      </div>
      <div className={styles.meta}>
        <div className={styles.metaLeft}>
          <span className={styles.metaItem}>
            <IconGitBranch size={12} />
            {branch}
          </span>
          <button
            className={styles.metaItem}
            type="button"
            title={workspace || "Open workspace"}
            onClick={() => void pickWorkspace()}
          >
            <IconMonitor size={12} />
            {workspace ? shortWorkspace(workspace) : "Open folder"}
          </button>
        </div>
        <div className={styles.metaRight} title={`${tokens.toLocaleString()} / ${contextMax.toLocaleString()} tokens`}>
          <ContextRing used={tokens} max={contextMax} />
        </div>
      </div>
    </div>
  );
}

function ThinkingPicker({
  value,
  disabled,
  onChange,
}: {
  value: ThinkingLevel;
  disabled?: boolean;
  onChange: (level: ThinkingLevel) => void;
}): JSX.Element {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const active = value !== "off";

  useEffect(() => {
    if (disabled) setOpen(false);
  }, [disabled]);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div className={styles.modePicker} ref={rootRef}>
      <button
        className={`${styles.iconBtn} ${active ? styles.iconBtnAccent : ""}`}
        type="button"
        title={value === "off" ? "Thinking" : `Thinking · ${value}`}
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
      >
        <IconThink size={15} />
      </button>
      {open && !disabled ? (
        <div className={styles.modeMenu}>
          {THINKING_OPTIONS.map((m) => (
            <button
              key={m.id}
              className={`${styles.modeOption} ${value === m.id ? styles.modeOptionActive : ""}`}
              type="button"
              onClick={() => {
                onChange(m.id);
                setOpen(false);
              }}
            >
              <span className={styles.modeLabel}>{m.label}</span>
              <span className={styles.modeDesc}>{m.desc}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
