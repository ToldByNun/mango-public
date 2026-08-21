export type ThinkingLevel = "off" | "think" | "deep" | "max";

const STORAGE_KEY = "mango.thinkingLevel";

const VALID: ThinkingLevel[] = ["off", "think", "deep", "max"];

export function loadThinkingLevel(): ThinkingLevel {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw && (VALID as string[]).includes(raw)) return raw as ThinkingLevel;
  } catch {
    /* ignore */
  }
  return "off";
}

export function saveThinkingLevel(level: ThinkingLevel): void {
  try {
    localStorage.setItem(STORAGE_KEY, level);
  } catch {
    /* ignore */
  }
}

export const THINKING_OPTIONS: Array<{ id: ThinkingLevel; label: string; desc: string }> = [
  { id: "off", label: "Off", desc: "Just go" },
  { id: "think", label: "Think", desc: "A beat longer" },
  { id: "deep", label: "Deep", desc: "Take the long way" },
  { id: "max", label: "Max", desc: "Leave no stone" },
];
