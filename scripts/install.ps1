#!/usr/bin/env pwsh
# Mango — one-shot setup: venv, packages, CLI, PATH.
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$AgentPy = Join-Path $Root "agent\python"
$VenvPy = Join-Path $AgentPy ".venv\Scripts\python.exe"
$VenvPip = Join-Path $AgentPy ".venv\Scripts\pip.exe"
$BinDir = Join-Path $Root "bin"
$ScriptsDir = Join-Path $AgentPy ".venv\Scripts"

function Add-UserPath([string]$Entry) {
    if (-not (Test-Path -LiteralPath $Entry)) { return $false }
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($null -eq $userPath) { $userPath = "" }
    $norm = $Entry.TrimEnd("\")
    foreach ($part in ($userPath -split ";")) {
        if ($part.TrimEnd("\") -eq $norm) { return $false }
    }
    $joined = if ($userPath) { "$userPath;$Entry" } else { $Entry }
    [Environment]::SetEnvironmentVariable("Path", $joined, "User")
    return $true
}

Write-Host "Mango install" -ForegroundColor DarkYellow
Write-Host "  root: $Root"

if (-not (Test-Path $VenvPy)) {
    Write-Host "Creating venv ..."
    python -m venv (Join-Path $AgentPy ".venv")
}

$packages = @(
    (Join-Path $Root "runtime\python"),
    (Join-Path $Root "tools\python"),
    (Join-Path $Root "context\python"),
    (Join-Path $Root "cot\python"),
    (Join-Path $Root "epistemic\python"),
    (Join-Path $Root "codeintel\python"),
    (Join-Path $Root "verification\python"),
    $AgentPy,
    (Join-Path $Root "cli\python")
)

Write-Host "Installing packages ..."
foreach ($pkg in $packages) {
    & $VenvPip install -e $pkg
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "Registering mango on user PATH ..."
$added = @()
if (Add-UserPath $BinDir) { $added += $BinDir }
if (Add-UserPath $ScriptsDir) { $added += $ScriptsDir }
& $VenvPy -m mango_cli.path_setup | Out-Host

if ($added.Count -gt 0) {
    Write-Host "Added to user PATH:" -ForegroundColor Green
    $added | ForEach-Object { Write-Host "  $_" }
}

if (-not (Test-Path (Join-Path $ScriptsDir "mango.exe"))) {
    Write-Host "WARN: mango.exe missing in venv Scripts" -ForegroundColor Red
}

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "  Close ALL terminals (including Cursor), open a new one:"
Write-Host "    cd your-project"
Write-Host "    mango"
