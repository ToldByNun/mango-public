import { app } from "electron";
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

/** Repo root in dev, or `resources/mango` when installed. */
export function findRepoRoot(): string {
  if (app.isPackaged) {
    return join(process.resourcesPath, "mango");
  }
  let dir = dirname(fileURLToPath(import.meta.url));
  for (let i = 0; i < 10; i += 1) {
    if (existsSync(join(dir, "runtime", "config.yaml")) && existsSync(join(dir, "agent", "python"))) {
      return dir;
    }
    dir = join(dir, "..");
  }
  return process.cwd();
}

export function pythonExecutable(repoRoot: string): string {
  const candidates =
    process.platform === "win32"
      ? [
          join(repoRoot, "python", "python.exe"),
          join(repoRoot, ".venv", "Scripts", "python.exe"),
          join(repoRoot, "agent", "python", ".venv", "Scripts", "python.exe"),
        ]
      : [
          join(repoRoot, "python", "bin", "python"),
          join(repoRoot, "python", "python"),
          join(repoRoot, ".venv", "bin", "python"),
          join(repoRoot, "agent", "python", ".venv", "bin", "python"),
        ];
  for (const path of candidates) {
    if (existsSync(path)) return path;
  }
  return process.platform === "win32" ? "python" : "python3";
}

/** Bundled template inside the install / dev repo. */
export function bundledRuntimeConfigExample(repoRoot: string): string {
  const example = join(repoRoot, "runtime", "config.example.yaml");
  if (existsSync(example)) return example;
  return join(repoRoot, "runtime", "config.yaml");
}

/** User-writable runtime config (never inside Program Files). */
export function userRuntimeConfigPath(): string {
  return join(app.getPath("userData"), "runtime", "config.yaml");
}

const DEFAULT_RUNTIME_YAML = `# Mango runtime config (user-writable)
model:
  path: ""
  n_ctx: 16384
  n_batch: 512

hardware:
  n_gpu_layers: -1
  n_threads: 0

inference:
  max_tokens: 2048
  temperature: 0.1
  top_p: 0.95
  stop: []
`;

/** Create userData/runtime/config.yaml from bundled example if missing. */
export function ensureUserRuntimeConfig(repoRoot: string): string {
  const target = userRuntimeConfigPath();
  if (existsSync(target)) return target;
  mkdirSync(dirname(target), { recursive: true });
  const seed = bundledRuntimeConfigExample(repoRoot);
  if (existsSync(seed)) {
    copyFileSync(seed, target);
  } else {
    writeFileSync(target, DEFAULT_RUNTIME_YAML, "utf8");
  }
  return target;
}

/** Effective config path passed to the Python sidecar. */
export function runtimeConfigPath(_repoRoot: string): string {
  return userRuntimeConfigPath();
}

export function promptsDir(repoRoot: string): string {
  return join(repoRoot, "prompts");
}
