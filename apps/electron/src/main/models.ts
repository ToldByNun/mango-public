import { existsSync, readdirSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { basename, join } from "node:path";
import { findRepoRoot } from "./paths";

export type GgufModel = {
  path: string;
  label: string;
};

const MAX_DEPTH = 5;

const BRAND_NAMES: Record<string, string> = {
  gemma: "Gemma", codegemma: "CodeGemma",
  qwen: "Qwen", qwen2: "Qwen2", "qwen2.5": "Qwen2.5", qwq: "QwQ",
  llama: "Llama", codellama: "CodeLlama", tinyllama: "TinyLlama",
  mistral: "Mistral", mixtral: "Mixtral", ministral: "Ministral", codestral: "Codestral", devstral: "Devstral",
  phi: "Phi", deepseek: "DeepSeek",
  grok: "Grok", yi: "Yi", glm: "GLM", chatglm: "ChatGLM",
  kimi: "Kimi", olmo: "OLMo", granite: "Granite",
  starcoder: "StarCoder", starcoder2: "StarCoder2",
  nemotron: "Nemotron", nvidia: "NVIDIA",
  mmproj: "mmproj",
};

const QUANT_RE = /\b(Q[0-9]_[A-Z_]+|[IF]Q[0-9S]_[A-Z0-9]+|[IF]\d{1,2})\b/i;
const SIZE_RE = /\b(\d+(\.\d+)?[BMK])\b/i;

function formatModelLabel(raw: string): string {
  const parts = raw.replace(/[-_]/g, " ").split(/\s+/);
  const out: string[] = [];
  let quant = "";
  let size = "";

  for (const p of parts) {
    const lower = p.toLowerCase();
    if (QUANT_RE.test(p)) {
      quant = p.toUpperCase().replace(/ /g, "_");
      continue;
    }
    const sizeMatch = SIZE_RE.exec(p);
    if (sizeMatch && !BRAND_NAMES[lower]) {
      size = sizeMatch[1].toUpperCase();
      continue;
    }
    const brand = BRAND_NAMES[lower];
    if (brand) {
      out.push(brand);
    } else if (/^\d/.test(p)) {
      out.push(p);
    } else {
      out.push(p.charAt(0).toUpperCase() + p.slice(1));
    }
  }

  const label = out.join(" ");
  const suffix = [size, quant].filter(Boolean).join(" ");
  return suffix ? `${label} ${suffix}` : label;
}

const MAX_MODELS = 200;

function discoverRoots(): string[] {
  const home = homedir();
  const repoRoot = findRepoRoot();
  const candidates = [
    join(home, ".cache", "lm-studio", "models"),
    join(home, ".lmstudio", "models"),
    join(home, ".ollama", "models"),
    join(repoRoot, "training", "output"),
    join(home, "AppData", "Local", "lm-studio", "models"),
    join(home, "AppData", "Local", "nomic.ai", "GPT4All"),
    join(home, "models"),
    join(home, "Downloads"),
  ];
  return [...new Set(candidates.filter((dir) => existsSync(dir)))];
}

function walkGguf(root: string, depth: number, out: GgufModel[]): void {
  if (depth > MAX_DEPTH || out.length >= MAX_MODELS) return;
  let entries: string[];
  try {
    entries = readdirSync(root);
  } catch {
    return;
  }
  for (const name of entries) {
    if (out.length >= MAX_MODELS) break;
    const full = join(root, name);
    let stat;
    try {
      stat = statSync(full);
    } catch {
      continue;
    }
    if (stat.isDirectory()) {
      walkGguf(full, depth + 1, out);
      continue;
    }
    if (!name.toLowerCase().endsWith(".gguf")) continue;
    out.push({
      path: full,
      label: formatModelLabel(basename(name, ".gguf")),
    });
  }
}

export function listGgufModels(): GgufModel[] {
  const found: GgufModel[] = [];
  const seen = new Set<string>();
  for (const root of discoverRoots()) {
    walkGguf(root, 0, found);
  }
  const unique: GgufModel[] = [];
  for (const item of found) {
    const key = item.path.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(item);
  }
  unique.sort((a, b) => a.label.localeCompare(b.label, undefined, { sensitivity: "base" }));
  return unique;
}
