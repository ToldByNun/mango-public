type IconProps = { size?: number };

export function IconPlus({ size = 16 }: IconProps): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M8 3v10M3 8h10" />
    </svg>
  );
}

export function IconThink({ size = 16 }: IconProps): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
      <circle cx="8" cy="6.5" r="3.2" />
      <path d="M6.2 9.6 5.4 13.2M9.8 9.6l.8 3.6M5.5 12.4h5" strokeLinecap="round" />
      <path d="M11.8 3.2c.9.4 1.5 1.3 1.5 2.4" strokeLinecap="round" />
      <path d="M13.2 2.4c1.2.6 2 1.8 2 3.2" strokeLinecap="round" opacity="0.55" />
    </svg>
  );
}

export function IconArrowUp({ size = 14 }: IconProps): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M8 12V4M8 4 4.5 7.5M8 4l3.5 3.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IconMic({ size = 16 }: IconProps): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
      <rect x="6" y="2.5" width="4" height="7" rx="2" />
      <path d="M4 8a4 4 0 0 0 8 0M8 12v2" strokeLinecap="round" />
    </svg>
  );
}

export function IconCheck({ size = 14 }: IconProps): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M3.5 8.5 6.5 11.5 12.5 4.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IconSearch({ size = 16 }: IconProps): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="7" cy="7" r="4" />
      <path d="M10.5 10.5 13 13" />
    </svg>
  );
}

export function IconGear({ size = 16 }: IconProps): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="8" cy="8" r="2.2" />
      <path d="M8 2.5v1.4M8 12.1v1.4M2.5 8h1.4M12.1 8h1.4M4.1 4.1l1 1M10.9 10.9l1 1M11.9 4.1l-1 1M5.1 10.9l-1 1" />
    </svg>
  );
}

export function IconSend({ size = 14 }: IconProps): JSX.Element {
  return <IconArrowUp size={size} />;
}

export function IconStop({ size = 10 }: IconProps): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 12 12" fill="currentColor">
      <rect x="1" y="1" width="10" height="10" rx="1.5" />
    </svg>
  );
}

export function IconUndo({ size = 16 }: IconProps): JSX.Element {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
    >
      <path
        d="M6.5 3.5L3 7l3.5 3.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M3 7h6a4 4 0 010 8H6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IconChevron({ open, size = 12 }: { open: boolean; size?: number }): JSX.Element {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 10 10"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      style={{ transform: open ? "rotate(180deg)" : "none", transition: "transform 150ms" }}
    >
      <path d="M2.5 4l2.5 2.5L7.5 4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IconFile({ size = 16 }: IconProps): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
      <path d="M4 2.5h5.5L12 5v8.5a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-10a1 1 0 0 1 1-1Z" />
      <path d="M9.5 2.5V5H12" />
    </svg>
  );
}

export function IconTest({ size = 16 }: IconProps): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
      <path d="M3 8.5 6 11.5 13 4.5" />
    </svg>
  );
}

export function IconTestFail({ size = 16 }: IconProps): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
      <path d="M4.5 4.5 11.5 11.5M11.5 4.5 4.5 11.5" />
    </svg>
  );
}

export function IconTestPending({ size = 16 }: IconProps): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
      <rect x="3" y="3" width="10" height="10" rx="1.5" />
      <path d="M5.5 8h5" />
    </svg>
  );
}

export function IconFolder({ size = 16 }: IconProps): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
      <path d="M2 4.5A1 1 0 0 1 3 3.5h3.2l1.3 1.5H13A1 1 0 0 1 14 6v6.5a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V4.5Z" />
    </svg>
  );
}

export function IconSparkles({ size = 16 }: IconProps): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
      <path d="M8 2v2M8 12v2M2 8h2M12 8h2M4.2 4.2l1.4 1.4M10.4 10.4l1.4 1.4M11.8 4.2l-1.4 1.4M5.6 10.4l-1.4 1.4" />
      <path d="M8 6.2l.6 1.4 1.4.6-1.4.6L8 10.2l-.6-1.4-1.4-.6 1.4-.6L8 6.2Z" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function IconZap({ size = 16 }: IconProps): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
      <path d="M9 2 4 9h3.5L7 14l5-7H8.5L9 2Z" />
    </svg>
  );
}

export function IconSliders({ size = 16 }: IconProps): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
      <path d="M2 4h12M2 8h12M2 12h12" />
      <circle cx="5" cy="4" r="1.2" fill="currentColor" />
      <circle cx="10" cy="8" r="1.2" fill="currentColor" />
      <circle cx="7" cy="12" r="1.2" fill="currentColor" />
    </svg>
  );
}

export function IconFilter({ size = 16 }: IconProps): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
      <path d="M2 3.5h12L9.5 8.5V12l-3 1.5V8.5L2 3.5Z" />
    </svg>
  );
}

export function IconGitBranch({ size = 16 }: IconProps): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
      <circle cx="5.5" cy="4" r="1.5" />
      <circle cx="5.5" cy="12" r="1.5" />
      <circle cx="11" cy="7" r="1.5" />
      <path d="M5.5 5.5v5M5.5 7H9a1.5 1.5 0 0 0 0-3H7.5" />
    </svg>
  );
}

export function IconCpu({ size = 16 }: IconProps): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
      <rect x="4.5" y="4.5" width="7" height="7" rx="1" />
      <path d="M6 2v1.5M10 2v1.5M6 12.5V14M10 12.5V14M2 6h1.5M2 10h1.5M12.5 6H14M12.5 10H14" />
    </svg>
  );
}

export function IconMonitor({ size = 16 }: IconProps): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
      <rect x="2.5" y="3" width="11" height="8" rx="1" />
      <path d="M6.5 13h3M8 11v2" strokeLinecap="round" />
    </svg>
  );
}

export function IconPlan({ size = 14 }: { size?: number }): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <path d="M3 4h10M3 8h6M3 12h8" />
    </svg>
  );
}

export function ContextRing({ used, max, size = 18 }: { used: number; max: number; size?: number }): JSX.Element {
  const radius = 7;
  const circumference = 2 * Math.PI * radius;
  const ratio = max > 0 ? Math.min(1, used / max) : 0;
  const offset = circumference * (1 - ratio);
  return (
    <svg width={size} height={size} viewBox="0 0 18 18" aria-label={`Context ${Math.round(ratio * 100)}%`}>
      <circle cx="9" cy="9" r={radius} fill="none" stroke="var(--border-strong)" strokeWidth="2" opacity="0.35" />
      <circle
        cx="9"
        cy="9"
        r={radius}
        fill="none"
        stroke="var(--text-secondary)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        transform="rotate(-90 9 9)"
      />
    </svg>
  );
}
