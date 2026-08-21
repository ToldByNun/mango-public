import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { app, BrowserWindow, dialog, ipcMain, Menu, session, shell } from "electron";
import { join } from "node:path";
import { gitBranch } from "./git";
import { findRepoRoot, runtimeConfigPath } from "./paths";
import { listGgufModels } from "./models";
import { loadSessions, saveSessions } from "./sessions";
import { speechActive, speechStart, speechStop } from "./speech";
import { Sidecar } from "./sidecar";
import { getStoredAuth, startDeviceFlow, clearAuth } from "./github";
import { checkForUpdatesManual, initAutoUpdater } from "./updater";
import type { AgentEvent, Session } from "../shared/events";

const repoRoot = findRepoRoot();
let mainWindow: BrowserWindow | null = null;
let sidecar: Sidecar | null = null;
let sessions: Session[] = [];
let workspace = "";
let modelLoaded = false;
let sidecarToolsFingerprint = "";

async function restartSidecarIfStale(): Promise<void> {
  if (!sidecar?.running) return;
  try {
    const health = await sidecar.request("health", {});
    const fp = String(health.run_tests_sha256_12 ?? "");
    if (fp && sidecarToolsFingerprint && fp !== sidecarToolsFingerprint) {
      console.warn("[sidecar] run_tests changed; restarting sidecar");
      await sidecar.stop();
      sidecar = null;
      modelLoaded = false;
    } else if (fp) {
      sidecarToolsFingerprint = fp;
    }
  } catch {
    await sidecar.stop().catch(() => undefined);
    sidecar = null;
    modelLoaded = false;
  }
}

async function ensureSidecar(): Promise<Sidecar> {
  await restartSidecarIfStale();
  if (sidecar?.running) return sidecar;
  sidecar = new Sidecar(repoRoot, workspace || repoRoot);
  sidecar.setEventHandler((event: AgentEvent) => {
    send("agent:event", event);
  });
  await sidecar.start();
  const health = await sidecar.request("health", {});
  sidecarToolsFingerprint = String(health.run_tests_sha256_12 ?? "");
  return sidecar;
}

function sessionsPath(): string {
  return join(app.getPath("userData"), "sessions.json");
}

function persist(): void {
  saveSessions(sessionsPath(), sessions);
}

function send(channel: string, payload: unknown): void {
  mainWindow?.webContents.send(channel, payload);
}

function registerIpc(): void {
  ipcMain.handle("sessions:list", () => sessions);
  ipcMain.handle("sessions:save", (_event, next: Session[]) => {
    sessions = next;
    persist();
    return sessions;
  });
  ipcMain.handle("workspace:get", () => workspace);
  ipcMain.handle("workspace:pick", async () => {
    const result = await dialog.showOpenDialog({
      title: "Open workspace",
      properties: ["openDirectory"],
    });
    if (result.canceled || !result.filePaths[0]) return workspace;
    const picked = result.filePaths[0];
    if (isMangoSource(picked)) {
      const isolated = join(app.getPath("userData"), "workspaces", "manual");
      mkdirSync(isolated, { recursive: true });
      workspace = isolated;
    } else {
      workspace = picked;
    }
    storeWorkspace(workspace);
    if (sidecar) sidecar.setWorkspace(workspace);
    return workspace;
  });
  ipcMain.handle("workspace:branch", async () => gitBranch(workspace));
  ipcMain.handle("workspace:set", async (_event, path: string) => {
    if (typeof path === "string" && path) {
      workspace = path;
      storeWorkspace(path);
      sidecar?.setWorkspace(path);
    }
    return workspace;
  });
  ipcMain.handle("files:pick", async () => {
    const result = await dialog.showOpenDialog({
      title: "Attach files",
      defaultPath: workspace || undefined,
      properties: ["openFile", "multiSelections"],
    });
    return result.canceled ? [] : result.filePaths;
  });
  ipcMain.handle("sidecar:status", () => ({
    ready: Boolean(sidecar?.running),
    modelLoaded,
  }));
  ipcMain.handle("sidecar:load", async () => {
    const child = await ensureSidecar();
    const result = await child.request("load_model", {});
    modelLoaded = true;
    return result;
  });
  ipcMain.handle("sidecar:settings", async () => {
    const child = await ensureSidecar();
    return child.request("get_settings", {});
  });
  ipcMain.handle("sidecar:set-model-path", async (_event, modelPath: string) => {
    const child = await ensureSidecar();
    const result = await child.request("set_model_path", { path: modelPath });
    modelLoaded = false;
    return result;
  });
  ipcMain.handle("sidecar:select-model", async (_event, modelPath: string) => {
    const child = await ensureSidecar();
    await child.request("set_model_path", { path: modelPath });
    await child.stop().catch(() => undefined);
    sidecar = null;
    modelLoaded = false;
    const next = await ensureSidecar();
    const result = await next.request("load_model", {});
    modelLoaded = true;
    return result;
  });
  ipcMain.handle("models:list", () => listGgufModels());
  ipcMain.handle(
    "agent:run",
    async (
      _event,
      payload: {
        sessionId: string;
        goal: string;
        workspace?: string;
        generateTitle?: boolean;
        thinkingLevel?: string;
        thoughtMaxTokens?: number | null;
      },
    ) => {
    const child = await ensureSidecar();
    const ws = resolveAgentWorkspace(payload.sessionId, payload.workspace);
    sidecar?.setWorkspace(ws);
    const thoughtRaw = payload.thoughtMaxTokens;
    const thoughtMaxTokens =
      typeof thoughtRaw === "number" && Number.isFinite(thoughtRaw)
        ? Math.max(32, Math.min(4096, Math.round(thoughtRaw)))
        : undefined;
    const result = await child.request("run", {
      session_id: payload.sessionId,
      goal: payload.goal,
      workspace: ws,
      generate_title: Boolean(payload.generateTitle),
      thinking_level: String(payload.thinkingLevel || "off"),
      ...(thoughtMaxTokens != null ? { thought_max_tokens: thoughtMaxTokens } : {}),
    });
    modelLoaded = true;
    const used = typeof result.workspace === "string" && result.workspace ? String(result.workspace) : ws;
    if (!workspace || isMangoSource(workspace)) {
      workspace = used;
      storeWorkspace(used);
    }
    return { ...result, workspace: used };
  });
  ipcMain.handle("agent:cancel", async (_event, sessionId: string) => {
    if (!sidecar?.running) return { ok: true };
    return sidecar.request("cancel", { session_id: sessionId });
  });
  ipcMain.handle("app:open-path", async (_event, target: string) => {
    await shell.openPath(target);
  });
  ipcMain.handle("app:config-path", () => runtimeConfigPath(repoRoot));
  ipcMain.handle("speech:start", (event, locale?: string) => {
    const ok = speechStart(
      typeof locale === "string" && locale ? locale : "de-DE",
      (text) => event.sender.send("speech:result", { text }),
      (message) => event.sender.send("speech:error", { message }),
    );
    return { ok, listening: ok };
  });
  ipcMain.handle("speech:stop", () => {
    speechStop();
    return { ok: true };
  });
  ipcMain.handle("speech:status", () => ({ listening: speechActive() }));

  ipcMain.handle("github:status", () => {
    const auth = getStoredAuth();
    if (!auth) return { loggedIn: false };
    return { loggedIn: true, user: auth.user };
  });
  ipcMain.handle("github:login", async () => {
    const flow = await startDeviceFlow();
    if (!flow) return { loggedIn: false, error: "Failed to start GitHub login. Check Client ID." };
    send("github:device-code", { userCode: flow.userCode, verificationUri: flow.verificationUri });
    const result = await flow.poll();
    if (result) return { loggedIn: true, user: result.user };
    return { loggedIn: false };
  });
  ipcMain.handle("github:logout", () => {
    clearAuth();
    return { loggedIn: false };
  });
  ipcMain.handle("app:version", () => app.getVersion());
  ipcMain.handle("app:check-updates", () => checkForUpdatesManual(() => mainWindow));
}

function resolveAppIcon(): string | undefined {
  const candidates = [
    join(repoRoot, "apps", "electron", "resources", "icon.png"),
    join(repoRoot, "apps", "electron", "src", "renderer", "src", "assets", "mango-logo.png"),
    join(__dirname, "../../resources/icon.png"),
  ];
  return candidates.find((p) => existsSync(p));
}

function createWindow(): void {
  const icon = resolveAppIcon();
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 840,
    minWidth: 1100,
    minHeight: 720,
    backgroundColor: "#0e0d0c",
    title: "Mango",
    frame: false,
    ...(icon ? { icon } : {}),
    webPreferences: {
      preload: preloadScript(),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });
  mainWindow.webContents.on("will-navigate", (e) => e.preventDefault());
  if (process.env.ELECTRON_RENDERER_URL) {
    mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL);
  } else {
    mainWindow.loadFile(join(__dirname, "../renderer/index.html"));
  }
}

app.whenReady().then(() => {
  if (process.platform === "win32") {
    app.setAppUserModelId("com.mango.app");
  }
  const icon = resolveAppIcon();
  if (process.platform === "darwin" && icon) {
    app.dock?.setIcon(icon);
  }
  session.defaultSession.setPermissionRequestHandler((_wc, permission, callback) => {
    callback(permission === "media" || permission === "audioCapture" || permission === "microphone");
  });
  session.defaultSession.setPermissionCheckHandler((_wc, permission) => {
    return permission === "media" || permission === "audioCapture" || permission === "microphone";
  });
  workspace = loadStoredWorkspace();
  sessions = loadSessions(sessionsPath());
  Menu.setApplicationMenu(null);

  ipcMain.on("win:minimize", () => mainWindow?.minimize());
  ipcMain.on("win:maximize", () => {
    if (mainWindow?.isMaximized()) mainWindow.unmaximize();
    else mainWindow?.maximize();
  });
  ipcMain.on("win:close", () => mainWindow?.close());

  registerIpc();
  createWindow();
  initAutoUpdater(() => mainWindow);
  ensureSidecar().catch((err: Error) => {
    console.error("sidecar failed", err);
    send("sidecar:error", String(err.message || err));
  });
});

app.on("window-all-closed", () => {
  persist();
  const child = sidecar;
  sidecar = null;
  void (async () => {
    try {
      await child?.stop();
    } catch {
      /* ignore */
    } finally {
      app.quit();
    }
  })();
});

function isMangoSource(path: string): boolean {
  return (
    existsSync(join(path, "runtime", "config.yaml")) &&
    existsSync(join(path, "agent", "python")) &&
    existsSync(join(path, "apps", "electron"))
  );
}

function workspaceStorePath(): string {
  return join(app.getPath("userData"), "workspace.json");
}

function loadStoredWorkspace(): string {
  try {
    const raw = readFileSync(workspaceStorePath(), "utf8");
    const data = JSON.parse(raw) as { path?: string };
    return typeof data.path === "string" ? data.path : "";
  } catch {
    return "";
  }
}

function storeWorkspace(path: string): void {
  writeFileSync(workspaceStorePath(), JSON.stringify({ path }, null, 2), "utf8");
}

function resolveAgentWorkspace(sessionId: string, requested?: string): string {
  for (const raw of [requested, workspace]) {
    if (!raw || isMangoSource(raw)) continue;
    mkdirSync(raw, { recursive: true });
    const resolved = raw;
    if (requested && resolved !== workspace) {
      workspace = resolved;
      storeWorkspace(resolved);
      sidecar?.setWorkspace(resolved);
    }
    return resolved;
  }
  return isolateWorkspace(sessionId);
}

function isolateWorkspace(sessionId: string): string {
  const isolated = join(app.getPath("userData"), "workspaces", sessionId || "default");
  mkdirSync(isolated, { recursive: true });
  return isolated;
}

function preloadScript(): string {
  const mjs = join(__dirname, "../preload/index.mjs");
  const js = join(__dirname, "../preload/index.js");
  return existsSync(mjs) ? mjs : js;
}
