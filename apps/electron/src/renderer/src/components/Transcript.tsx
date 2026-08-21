import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { TranscriptBlock } from "@shared/events";
import { useAgent } from "../context/AgentSession";
import { shortPath } from "../lib/session";
import { stripThoughtMarkup } from "../lib/thoughtSanitize";
import {
  experimentStatusMeta,
  parseUnifiedDiff,
  segmentActivity,
  splitTurn,
  type ActivitySegment,
  type DiffLine,
  type ExperimentBlock,
  type FileBlock,
  type ThoughtBlock,
  type ToolBlock,
} from "../lib/turnActivity";
import styles from "../styles/transcript.module.css";
import { IconChevron, IconFile, IconTest, IconTestFail, IconTestPending } from "./Icons";

const STARTERS = ["Fix failing tests", "Explain this repo", "Add a feature"];

function groupTurns(messages: TranscriptBlock[]): TranscriptBlock[][] {
  const turns: TranscriptBlock[][] = [];
  let current: TranscriptBlock[] = [];
  for (const block of messages) {
    if (block.kind === "user" && current.length > 0) {
      turns.push(current);
      current = [];
    }
    current.push(block);
  }
  if (current.length > 0) turns.push(current);
  return turns;
}

function renderInlineCode(text: string): ReactNode {
  const parts = text.split(/(`[^`]+`)/g);
  return parts.map((part, i) => {
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return (
        <code key={i} className={styles.inlineCode}>
          {part.slice(1, -1)}
        </code>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

export function Transcript(): JSX.Element {
  const { active, send, setDiff } = useAgent();
  const ref = useRef<HTMLDivElement>(null);
  const [pinned, setPinned] = useState(true);
  const running = active?.status === "running";
  const messages = active?.messages ?? [];
  const turns = useMemo(() => groupTurns(messages), [messages]);

  useEffect(() => {
    if (pinned && ref.current) {
      ref.current.scrollTop = ref.current.scrollHeight;
    }
  }, [messages, pinned, running]);

  const onScroll = (): void => {
    const el = ref.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
    setPinned(atBottom);
  };

  if (!active || messages.length === 0) {
    return (
      <div className={styles.wrap}>
        <div className={styles.empty}>
          <p className={styles.emptyBrand}>Mango</p>
          <h1>What should we work on?</h1>
          <p className={styles.emptySub}>Build, fix, or explain — pick a workspace and ask.</p>
          <div className={styles.chips}>
            {STARTERS.map((label) => (
              <button
                key={label}
                className={styles.chip}
                type="button"
                disabled={running}
                onClick={() => void send(label, [])}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.frame}>
      <div className={styles.wrap} ref={ref} onScroll={onScroll}>
        <div className={styles.inner}>
          {turns.map((turn, index) => {
            const isActiveTurn = index === turns.length - 1 && running;
            const { user, activity, finale } = splitTurn(turn);
            return (
              <div key={turn[0]?.id ?? index} className={styles.turn}>
                {user && user.kind === "user" ? (
                  <div className={`${styles.entry} ${styles.entry_user}`}>
                    <div className={styles.user}>{user.text}</div>
                  </div>
                ) : null}
                <ActivityStream
                  blocks={activity}
                  active={isActiveTurn}
                  onDiff={setDiff}
                />
                {finale.map((item) => (
                  <div
                    key={item.id}
                    className={`${styles.entry} ${item.kind === "final" ? styles.entry_final : styles.entry_error}`}
                  >
                    {item.kind === "final" ? (
                      <div className={styles.final}>
                        {item.text}
                        {item.streaming ? <span className={styles.caret} /> : null}
                      </div>
                    ) : item.kind === "error" ? (
                      <div className={styles.error}>{item.text}</div>
                    ) : null}
                  </div>
                ))}
              </div>
            );
          })}
          {running ? <div className={styles.spinner} /> : null}
        </div>
      </div>
      {!pinned ? (
        <button
          className={styles.jump}
          type="button"
          onClick={() => {
            setPinned(true);
            if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
          }}
        >
          Jump to latest
        </button>
      ) : null}
    </div>
  );
}

function ActivityStream({
  blocks,
  active,
  onDiff,
}: {
  blocks: TranscriptBlock[];
  active: boolean;
  onDiff: (value: { path: string; diff: string } | null) => void;
}): JSX.Element | null {
  const segments = useMemo(() => segmentActivity(blocks), [blocks]);
  const streamingId = useMemo(() => {
    for (let i = segments.length - 1; i >= 0; i -= 1) {
      const seg = segments[i];
      if (seg.kind === "thoughts" && seg.streaming) return seg.id;
      if (seg.kind === "tool" && seg.item.streaming) return seg.id;
    }
    return null;
  }, [segments]);
  const lastId = segments.length > 0 ? segments[segments.length - 1].id : null;

  // Manual open overrides; cleared when a new stream starts so previous rows collapse.
  const [manual, setManual] = useState<Record<string, boolean>>({});
  const prevStream = useRef<string | null>(null);
  useEffect(() => {
    if (streamingId && streamingId !== prevStream.current) {
      setManual({});
      prevStream.current = streamingId;
    }
    if (!streamingId) prevStream.current = null;
  }, [streamingId]);

  if (segments.length === 0) return null;

  return (
    <div className={`${styles.activity} ${active ? styles.activityLive : ""}`}>
      {segments.map((seg) => {
        // Auto-expand while streaming; keep latest thought open until the next activity arrives.
        const holdLatestThought =
          active &&
          !streamingId &&
          seg.id === lastId &&
          seg.kind === "thoughts";
        const forceOpen = streamingId === seg.id || holdLatestThought;
        const open = forceOpen || Boolean(manual[seg.id]);
        return (
          <StatusRow
            key={seg.id}
            segment={seg}
            open={open}
            forceOpen={forceOpen}
            onToggle={() => {
              if (forceOpen) return;
              setManual((prev) => ({ ...prev, [seg.id]: !prev[seg.id] }));
            }}
            onDiff={onDiff}
          />
        );
      })}
    </div>
  );
}

function StatusRow({
  segment,
  open,
  forceOpen,
  onToggle,
  onDiff,
}: {
  segment: ActivitySegment;
  open: boolean;
  forceOpen: boolean;
  onToggle: () => void;
  onDiff: (value: { path: string; diff: string } | null) => void;
}): JSX.Element | null {
  if (segment.kind === "thoughts") {
    const body = segment.items
      .map((t) => stripThoughtMarkup(t.text || ""))
      .filter(Boolean)
      .join("\n\n");
    if (!body.trim() && !segment.streaming) {
      return null as unknown as JSX.Element;
    }
    return (
      <ThoughtStatus
        items={segment.items}
        durationMs={segment.durationMs}
        streaming={segment.streaming}
        open={open}
        onToggle={onToggle}
      />
    );
  }
  if (segment.kind === "file") {
    return <FileStatus item={segment.item} open={open} onToggle={onToggle} onDiff={onDiff} />;
  }
  if (segment.kind === "tool") {
    return <ToolStatus item={segment.item} open={open || forceOpen} onToggle={onToggle} />;
  }
  if (segment.kind === "verification") {
    return (
      <div className={styles.statusRow}>
        <span className={styles.statusVerb}>{segment.item.ok ? "Passed" : "Failed"}</span>
        <span className={styles.statusMeta}> verification</span>
        {open ? <div className={styles.statusBody}>{segment.item.report}</div> : null}
      </div>
    );
  }
  if (segment.kind === "syntax") {
    return (
      <div className={styles.statusRow}>
        <span className={styles.statusVerb}>Syntax</span>
        <span className={styles.statusMeta}>
          {" "}
          {shortPath(segment.item.path)} {segment.item.message}
        </span>
      </div>
    );
  }
  if (segment.kind === "experiment") {
    return <ExperimentStatus item={segment.item} open={open} onToggle={onToggle} />;
  }
  return (
    <div className={styles.statusRow}>
      <span className={styles.statusMeta}>{segment.item.text}</span>
    </div>
  );
}

function ExperimentStatus({
  item,
  open,
  onToggle,
}: {
  item: ExperimentBlock;
  open: boolean;
  onToggle: () => void;
}): JSX.Element {
  const meta = experimentStatusMeta(item);
  const unit = item.unit || "ms";
  const lines = [
    item.hypothesis ? `Hypothesis: ${item.hypothesis}` : "",
    item.before != null ? `Before ${item.before} ${unit}` : "",
    item.after != null ? `After ${item.after} ${unit}` : "",
    item.reason && item.reason !== "keep" ? `Reason: ${item.reason.replace(/_/g, " ")}` : "",
  ].filter(Boolean);
  const hasBody = lines.length > 0;
  return (
    <div className={styles.statusRow}>
      <button className={styles.statusHead} type="button" onClick={() => hasBody && onToggle()}>
        <span className={styles.statusVerb}>Experiment</span>
        <span className={item.decision === "revert" ? styles.statusDel : styles.statusAdd}>
          {" "}
          {item.decision}
        </span>
        <span className={styles.statusMeta}> {meta}</span>
        {hasBody ? (
          <span className={styles.statusChevron}>
            <IconChevron open={open} size={10} />
          </span>
        ) : null}
      </button>
      {open && hasBody ? <div className={styles.statusBody}>{lines.join("\n")}</div> : null}
    </div>
  );
}

function ThoughtStatus({
  items,
  durationMs,
  streaming,
  open,
  onToggle,
}: {
  items: ThoughtBlock[];
  durationMs: number;
  streaming: boolean;
  open: boolean;
  onToggle: () => void;
}): JSX.Element {
  const seconds = Math.max(streaming ? 0 : 1, Math.round(durationMs / 1000));
  const label = streaming ? "Thinking…" : `Thought for ${seconds}s`;
  const body = items
    .map((t) => stripThoughtMarkup(t.text || ""))
    .filter(Boolean)
    .join("\n\n");
  const show = open || streaming;

  return (
    <div className={`${styles.statusRow} ${styles.statusThought}`}>
      <button className={styles.statusHead} type="button" onClick={onToggle}>
        <span className={styles.statusVerb}>{label}</span>
        <span className={styles.statusChevron}>
          <IconChevron open={show} size={10} />
        </span>
      </button>
      {show ? (
        <div className={styles.statusBody}>
          {body ? renderInlineCode(body) : null}
          {streaming ? <span className={styles.caret} aria-hidden /> : null}
        </div>
      ) : null}
    </div>
  );
}

function FileStatus({
  item,
  open,
  onToggle,
  onDiff,
}: {
  item: FileBlock;
  open: boolean;
  onToggle: () => void;
  onDiff: (value: { path: string; diff: string } | null) => void;
}): JSX.Element {
  const hasDiff = Boolean(item.diff && item.action !== "read");
  const label = item.action === "read" ? "Read" : item.action === "created" ? "Created" : "Edited";
  const actionClass =
    item.action === "read" ? styles.badgeRead : item.action === "created" ? styles.badgeCreated : styles.badgeEdited;
  const range =
    item.action === "read" && item.startLine != null && item.endLine != null
      ? ` L${item.startLine}-${item.endLine}`
      : "";

  return (
    <div className={styles.widgetRow}>
      <button
        className={`${styles.badge} ${actionClass}`}
        type="button"
        onClick={() => {
          if (hasDiff) onToggle();
          else {
            const target = item.absolutePath ?? item.path;
            if (item.diff) onDiff({ path: target, diff: item.diff });
            else void window.mango.app.openPath(target);
          }
        }}
      >
        <IconFile size={12} />
        <span className={styles.badgeLabel}>
          {label} <span className={styles.badgePath}>{shortPath(item.path)}</span>
          {range ? <span className={styles.badgeRange}>{range}</span> : null}
        </span>
        {item.added ? <span className={styles.add}>+{item.added}</span> : null}
        {item.removed ? <span className={styles.del}>-{item.removed}</span> : null}
        {hasDiff ? (
          <span className={styles.statusChevron}>
            <IconChevron open={open} size={10} />
          </span>
        ) : null}
      </button>
      {open && hasDiff && item.diff ? (
        <div className={styles.diffBlock}>
          <InlineDiff diff={item.diff} />
          <button
            className={styles.diffOpen}
            type="button"
            onClick={() => onDiff({ path: item.absolutePath ?? item.path, diff: item.diff || "" })}
          >
            Open full diff
          </button>
        </div>
      ) : null}
    </div>
  );
}

function ToolStatus({
  item,
  open,
  onToggle,
}: {
  item: ToolBlock;
  open: boolean;
  onToggle: () => void;
}): JSX.Element {
  const hasBody = Boolean((item.body ?? "").trim());
  const show = open || Boolean(item.streaming);
  const lines = (item.body ?? "").split("\n");
  const body = lines.slice(0, 40).join("\n") + (lines.length > 40 ? "\n…" : "");
  const running = Boolean(item.streaming);
  const blocked = Boolean(item.blocked);
  const passed = !blocked && item.ok === true;
  const failed = blocked || item.ok === false;

  return (
    <div className={`${styles.widgetRow} ${styles.tool} ${passed ? styles.toolPass : ""} ${failed ? styles.toolFail : ""} ${running ? styles.toolRunning : ""}`}>
      <button
        className={`${styles.badge} ${styles.badgeTool} ${failed ? styles.badgeFail : ""} ${blocked ? styles.badgeBlocked : ""} ${running ? styles.badgeRunning : ""} ${passed ? styles.badgePass : ""}`}
        type="button"
        onClick={() => {
          if (hasBody || running) onToggle();
        }}
      >
        {running ? (
          <span className={styles.badgeSpinner} aria-hidden />
        ) : blocked ? (
          <IconTestPending size={12} />
        ) : passed ? (
          <IconTest size={12} />
        ) : failed ? (
          <IconTestFail size={12} />
        ) : (
          <IconTestPending size={12} />
        )}
        <span className={styles.badgeLabel}>{blocked ? "Runner blocked" : item.title}</span>
        {passed ? <span className={styles.badgeOk}>pass</span> : null}
        {blocked ? <span className={styles.badgeBlockedTag}>blocked</span> : null}
        {failed && !blocked ? <span className={styles.badgeFailTag}>fail</span> : null}
        {running ? <span className={styles.badgePendingTag}>running</span> : null}
        {hasBody ? (
          <span className={styles.statusChevron}>
            <IconChevron open={show} size={10} />
          </span>
        ) : null}
      </button>
      {show && hasBody ? (
        <div className={`${styles.embedBody} ${item.console ? styles.console : styles.toolBody}`}>{body}</div>
      ) : null}
    </div>
  );
}

function InlineDiff({ diff }: { diff: string }): JSX.Element {
  const lines = useMemo(() => parseUnifiedDiff(diff, 60), [diff]);
  return (
    <div className={styles.diffView}>
      {lines.map((line, i) => (
        <DiffRow key={`${i}-${line.type}-${line.text.slice(0, 24)}`} line={line} />
      ))}
    </div>
  );
}

function DiffRow({ line }: { line: DiffLine }): JSX.Element {
  if (line.type === "hunk" || line.type === "meta") {
    return <div className={styles.diffMeta}>{line.text}</div>;
  }
  const cls =
    line.type === "add" ? styles.diffAdd : line.type === "del" ? styles.diffDel : styles.diffCtx;
  const num = line.type === "del" ? line.oldNo : line.newNo;
  return (
    <div className={`${styles.diffLine} ${cls}`}>
      <span className={styles.diffNum}>{num ?? ""}</span>
      <span className={styles.diffSign}>
        {line.type === "add" ? "+" : line.type === "del" ? "-" : " "}
      </span>
      <span className={styles.diffText}>{line.text || " "}</span>
    </div>
  );
}
