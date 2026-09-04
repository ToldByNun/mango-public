import { existsSync } from "node:fs";
import { app, BrowserWindow, Menu, session } from "electron";
import { join } from "node:path";
import { destroyAuthStore } from "./github";
import { findRepoRoot, ensureUserRuntimeConfig, runtimeConfigPath } from "./paths";
import { initAutoUpdater } from "./updater";
import { SessionService } from "./services/session.service";
import { WorkspaceService } from "./services/workspace.service";
import { SidecarService } from "./services/sidecar.service";
import { AgentService } from "./services/agent.service";
import { registerSessionIpc } from "./ipc/sessions.ipc";
import { registerWorkspaceIpc } from "./ipc/workspace.ipc";
import { registerSidecarIpc } from "./ipc/sidecar.ipc";
import { registerAgentIpc } from "./ipc/agent.ipc";
import { registerAppIpc, registerWindowIpc } from "./ipc/app.ipc";

const repoRoot = findRepoRoot();
const runtimeConfig = ensureUserRuntimeConfig(repoRoot);
let mainWindow: BrowserWindow | null = null;

const sessions = new SessionService();
const workspace = new WorkspaceService();

function send(channel: string, payload: unknown): void {
  mainWindow?.webContents.send(channel, payload);
}

const sidecar = new SidecarService(
  repoRoot,
  runtimeConfig,
  () => workspace.get(),
  send,
  () => mainWindow,
);
const agent = new AgentService(sidecar, workspace);

workspace.setChangeHandler((path) => sidecar.setWorkspace(path));

function registerIpc(): void {
  registerSessionIpc(sessions);
  registerWorkspaceIpc(workspace);
  registerSidecarIpc(sidecar);
  registerAgentIpc(agent);
  registerAppIpc({
    runtimeConfigPath: runtimeConfigPath(repoRoot),
    getMainWindow: () => mainWindow,
    send,
  });
  registerWindowIpc(() => mainWindow);
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
    show: false,
    ...(icon ? { icon } : {}),
    webPreferences: {
      preload: preloadScript(),
      contextIsolation: true,
      nodeIntegration: false,
      // sandbox:false — webUtils.getPathForFile (drag-drop) + native speech need non-sandbox preload
      sandbox: false,
    },
  });
  mainWindow.once("ready-to-show", () => mainWindow?.show());
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
  workspace.loadStored();
  sessions.load();
  Menu.setApplicationMenu(null);

  registerIpc();
  createWindow();
  initAutoUpdater(() => mainWindow);
  sidecar.ensure().catch((err: Error) => {
    console.error("sidecar failed", err);
    send("sidecar:error", String(err.message || err));
  });
});

// Graceful shutdown prevents the Python sidecar from being force-killed while
// it still holds GPU memory. A force-kill on Windows can crash the NVIDIA driver.
let isQuitting = false;
app.on("before-quit", (event) => {
  if (isQuitting) return;
  event.preventDefault();
  isQuitting = true;
  sessions.destroy();
  workspace.destroy();
  destroyAuthStore();
  void (async () => {
    try {
      await sidecar.stop();
    } catch {
      /* ignore */
    } finally {
      app.quit();
    }
  })();
});

app.on("window-all-closed", () => {
  app.quit();
});

function preloadScript(): string {
  const mjs = join(__dirname, "../preload/index.mjs");
  const js = join(__dirname, "../preload/index.js");
  return existsSync(mjs) ? mjs : js;
}
