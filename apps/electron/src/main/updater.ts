import { app, BrowserWindow, dialog } from "electron";
import updater from "electron-updater";

const { autoUpdater } = updater;

let checking = false;

function showBox(
  win: BrowserWindow | null,
  options: Electron.MessageBoxOptions,
): Promise<Electron.MessageBoxReturnValue> {
  return win ? dialog.showMessageBox(win, options) : dialog.showMessageBox(options);
}

export function initAutoUpdater(getMainWindow: () => BrowserWindow | null): void {
  if (!app.isPackaged) return;

  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = true;

  autoUpdater.on("update-available", (info) => {
    console.log(`[updater] update available: ${info.version}`);
  });

  autoUpdater.on("update-downloaded", (info) => {
    void showBox(getMainWindow(), {
      type: "info",
      title: "Update ready",
      message: `Mango ${info.version} is ready to install.`,
      detail: "Restart now to apply the update, or later when you quit.",
      buttons: ["Restart now", "Later"],
      defaultId: 0,
      cancelId: 1,
    }).then(({ response }) => {
      if (response === 0) {
        autoUpdater.quitAndInstall(false, true);
      }
    });
  });

  autoUpdater.on("error", (err) => {
    console.error("[updater]", err);
  });

  setTimeout(() => {
    void autoUpdater.checkForUpdates().catch((err: unknown) => {
      console.error("[updater] check failed", err);
    });
  }, 8_000);
}

export async function checkForUpdatesManual(
  getMainWindow: () => BrowserWindow | null,
): Promise<{ ok: boolean; message: string }> {
  if (!app.isPackaged) {
    return { ok: false, message: "Updates only work in the installed Mango app (not npm run dev)." };
  }
  if (checking) {
    return { ok: true, message: "Already checking for updates…" };
  }
  checking = true;
  try {
    const result = await autoUpdater.checkForUpdates();
    const latest = result?.updateInfo?.version;
    const current = app.getVersion();
    if (!latest || latest === current) {
      const message = `Mango ${current} is up to date.`;
      await showBox(getMainWindow(), { type: "info", title: "Mango", message });
      return { ok: true, message };
    }
    return { ok: true, message: `Update ${latest} found. Downloading…` };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    await showBox(getMainWindow(), { type: "error", title: "Update check failed", message });
    return { ok: false, message };
  } finally {
    checking = false;
  }
}
