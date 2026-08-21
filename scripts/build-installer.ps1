#!/usr/bin/env pwsh
# Build a Windows NSIS installer for Mango (Electron + Python sidecar).
# Usage:
#   .\scripts\build-installer.ps1
#   .\scripts\build-installer.ps1 -SkipSidecar   # UI-only package (needs system Python)
#   .\scripts\build-installer.ps1 -Publish       # upload GitHub Release (needs GH_TOKEN)
#   .\build.cmd
param(
    [switch]$SkipSidecar,
    [switch]$Publish,
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Electron = Join-Path $Root "apps\electron"
$RuntimeOut = Join-Path $Electron "build\mango-runtime"
$IconSrc = Join-Path $Electron "src\renderer\src\assets\mango-logo.png"
$IconDstDir = Join-Path $Electron "resources"
$IconDst = Join-Path $IconDstDir "icon.png"
$ReleaseDir = Join-Path $Electron "release"

function Assert-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name"
    }
}

Write-Host "Mango installer build" -ForegroundColor DarkYellow
Write-Host "  root: $Root"

Assert-Command "node"
Assert-Command "npm"
if (-not $SkipSidecar) {
    Assert-Command "python"
}

if ($Version) {
    $pkgPath = Join-Path $Electron "package.json"
    node -e "const fs=require('fs');const p=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));p.version=process.argv[2];fs.writeFileSync(process.argv[1], JSON.stringify(p,null,2)+'\n');" $pkgPath $Version
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "  version -> $Version"
}

# --- icon ---
New-Item -ItemType Directory -Force -Path $IconDstDir | Out-Null
if (Test-Path -LiteralPath $IconSrc) {
    Copy-Item -LiteralPath $IconSrc -Destination $IconDst -Force
} else {
    Write-Host "WARN: mango-logo.png missing; electron-builder may use a default icon" -ForegroundColor Yellow
}

# --- mango-runtime (sidecar) ---
if (Test-Path -LiteralPath $RuntimeOut) {
    Remove-Item -LiteralPath $RuntimeOut -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $RuntimeOut | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RuntimeOut "runtime") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RuntimeOut "agent\python") | Out-Null

Copy-Item -LiteralPath (Join-Path $Root "prompts") -Destination (Join-Path $RuntimeOut "prompts") -Recurse -Force
Copy-Item -LiteralPath (Join-Path $Root "runtime\config.yaml") -Destination (Join-Path $RuntimeOut "runtime\config.yaml") -Force

# Marker so packaged tree looks like a Mango root (paths / health checks).
Set-Content -Path (Join-Path $RuntimeOut "agent\python\.mango-runtime") -Value "bundled" -Encoding ascii

if (-not $SkipSidecar) {
    Write-Host "Creating bundled Python venv (llama-cpp-python can take a while) ..."
    $venvPy = Join-Path $RuntimeOut ".venv\Scripts\python.exe"
    $venvPip = Join-Path $RuntimeOut ".venv\Scripts\pip.exe"
    python -m venv (Join-Path $RuntimeOut ".venv")
    & $venvPip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $packages = @(
        (Join-Path $Root "runtime\python"),
        (Join-Path $Root "tools\python"),
        (Join-Path $Root "context\python"),
        (Join-Path $Root "cot\python"),
        (Join-Path $Root "epistemic\python"),
        (Join-Path $Root "codeintel\python"),
        (Join-Path $Root "verification\python"),
        (Join-Path $Root "agent\python"),
        (Join-Path $Root "cli\python")
    )
    foreach ($pkg in $packages) {
        Write-Host "  pip install $pkg"
        & $venvPip install $pkg
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }

    if (-not (Test-Path -LiteralPath $venvPy)) {
        throw "Bundled python missing after venv create: $venvPy"
    }
} else {
    Write-Host "SkipSidecar: installer will use system Python on PATH" -ForegroundColor Yellow
}

# --- Electron deps + package ---
Push-Location $Electron
try {
    if (-not (Test-Path (Join-Path $Electron "node_modules\electron-builder"))) {
        Write-Host "npm install ..."
        npm install
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }

    Write-Host "electron-vite build ..."
    npm run build
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $publishMode = if ($Publish) { "always" } else { "never" }
    Write-Host "electron-builder (publish=$publishMode) ..."
    npx electron-builder --publish $publishMode
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "Done." -ForegroundColor Green
if (Test-Path -LiteralPath $ReleaseDir) {
    Write-Host "Artifacts:"
    Get-ChildItem -LiteralPath $ReleaseDir -File |
        Where-Object { $_.Extension -in ".exe", ".yml", ".yaml", ".blockmap" } |
        ForEach-Object { Write-Host "  $($_.FullName)" }
}
Write-Host ""
Write-Host "Share the Mango-Setup-*.exe installer. Auto-updates need a GitHub Release"
Write-Host "(run with -Publish, or upload the release/ folder assets yourself)."
