import { app } from "electron";
import { existsSync } from "node:fs";
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
          join(repoRoot, ".venv", "Scripts", "python.exe"),
          join(repoRoot, "agent", "python", ".venv", "Scripts", "python.exe"),
        ]
      : [
          join(repoRoot, ".venv", "bin", "python"),
          join(repoRoot, "agent", "python", ".venv", "bin", "python"),
        ];
  for (const path of candidates) {
    if (existsSync(path)) return path;
  }
  return process.platform === "win32" ? "python" : "python3";
}

export function runtimeConfigPath(repoRoot: string): string {
  return join(repoRoot, "runtime", "config.yaml");
}

export function promptsDir(repoRoot: string): string {
  return join(repoRoot, "prompts");
}
