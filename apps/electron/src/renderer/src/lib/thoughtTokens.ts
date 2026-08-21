const STORAGE_KEY = "mango.thoughtMaxTokens";

/** null = use Thinking-level preset */
export function loadThoughtMaxTokens(): number | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw == null || raw === "" || raw === "auto") return null;
    const n = Number(raw);
    if (Number.isFinite(n) && n >= 32 && n <= 4096) return Math.round(n);
  } catch {
    /* ignore */
  }
  return null;
}

export function saveThoughtMaxTokens(value: number | null): void {
  try {
    if (value == null) localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, String(Math.round(value)));
  } catch {
    /* ignore */
  }
}

export const THOUGHT_TOKEN_PRESETS: Record<string, number> = {
  off: 128,
  think: 256,
  deep: 384,
  max: 512,
};
