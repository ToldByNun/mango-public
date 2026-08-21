import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";

let active: ChildProcessWithoutNullStreams | null = null;
let intentionalStop = false;

function windowsScript(locale: string): string {
  const safeLocale = locale.replace(/"/g, "");
  return `
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech
$engine = $null
foreach ($name in @("${safeLocale}", "de-DE", "en-US")) {
  try {
    $culture = [System.Globalization.CultureInfo]::GetCultureInfo($name)
    $engine = New-Object System.Speech.Recognition.SpeechRecognitionEngine($culture)
    break
  } catch {}
}
if ($null -eq $engine) {
  Write-Error "No speech recognizer installed for ${safeLocale}."
  exit 1
}
$engine.SetInputToDefaultAudioDevice()
$engine.BabbleTimeout = [TimeSpan]::FromSeconds(0)
$engine.InitialSilenceTimeout = [TimeSpan]::FromSeconds(8)
$engine.EndSilenceTimeout = [TimeSpan]::FromSeconds(0.9)
$result = $engine.Recognize()
if ($null -eq $result) { exit 2 }
Write-Output $result.Text
`.trim();
}

export function speechActive(): boolean {
  return active != null;
}

export function speechStop(): void {
  if (!active) return;
  intentionalStop = true;
  active.kill();
  active = null;
}

export function speechStart(
  locale: string,
  onResult: (text: string) => void,
  onError: (message: string) => void,
): boolean {
  if (process.platform !== "win32") {
    onError("Voice input is only supported on Windows in this build.");
    return false;
  }
  if (active) return false;

  const child = spawn(
    "powershell.exe",
    ["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", windowsScript(locale)],
    { windowsHide: true, stdio: ["ignore", "pipe", "pipe"] },
  );
  active = child;

  let stdout = "";
  let stderr = "";
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdout.on("data", (chunk: string) => {
    stdout += chunk;
  });
  child.stderr.on("data", (chunk: string) => {
    stderr += chunk;
  });

  child.on("error", (err) => {
    active = null;
    intentionalStop = false;
    onError(err.message || "Speech process failed");
  });

  child.on("close", (code) => {
    active = null;
    if (intentionalStop) {
      intentionalStop = false;
      return;
    }
    const text = stdout.trim();
    if (code === 0 && text) {
      onResult(text);
      return;
    }
    const detail = stderr.trim().split("\n").pop()?.trim();
    if (code === 2 || !text) {
      onError(detail || "No speech detected — try again.");
      return;
    }
    onError(detail || "Speech recognition failed.");
  });

  return true;
}
