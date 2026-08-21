import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

export async function gitBranch(workspace: string): Promise<string> {
  if (!workspace) return "no git";
  try {
    const { stdout } = await execFileAsync("git", ["rev-parse", "--abbrev-ref", "HEAD"], {
      cwd: workspace,
      windowsHide: true,
    });
    const name = stdout.trim();
    return name || "no git";
  } catch {
    return "no git";
  }
}
