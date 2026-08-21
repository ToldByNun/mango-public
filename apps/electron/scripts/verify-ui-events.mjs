/** UI event mapping checks for renderer session.ts (no build step). */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const sessionPath = join(here, "..", "src", "renderer", "src", "lib", "session.ts");
const agentPath = join(here, "..", "src", "renderer", "src", "context", "AgentSession.tsx");
const preloadPath = join(here, "..", "src", "preload", "index.ts");
const transcriptPath = join(here, "..", "src", "renderer", "src", "components", "Transcript.tsx");

const session = readFileSync(sessionPath, "utf8");
const agent = readFileSync(agentPath, "utf8");
const preload = readFileSync(preloadPath, "utf8");
const transcript = readFileSync(transcriptPath, "utf8");

const checks = [
  [session.includes('case "agent.file"'), "session maps agent.file"],
  [session.includes("absolutePath"), "session stores absolutePath"],
  [session.includes('case "agent.tool"'), "session maps agent.tool"],
  [session.includes("upsertTool"), "session upserts tool badges"],
  [agent.includes("agent.run(sessionId, userText, runWorkspace)"), "renderer passes workspace to IPC"],
  [agent.includes("api().workspace.pick()"), "send prompts for workspace when empty"],
  [preload.includes("workspace?: string"), "preload forwards workspace"],
  [transcript.includes("IconTestFail"), "transcript shows test fail icon"],
  [transcript.includes("badgePass"), "transcript styles passing tests"],
  [transcript.includes("shortPath(item.path)"), "transcript shortens file paths"],
];

for (const [ok, label] of checks) {
  if (!ok) {
    console.error(`FAIL ${label}`);
    process.exit(1);
  }
  console.log(`OK ${label}`);
}

console.log("PASS ui static verification");
