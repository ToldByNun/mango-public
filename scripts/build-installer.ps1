#!/usr/bin/env pwsh
# Build a Windows NSIS installer for Mango (Electron + portable Python sidecar).
# Usage:
#   .\scripts\build-installer.ps1
#   .\scripts\build-installer.ps1 -SkipSidecar   # UI-only package (needs system Python)
#   .\scripts\build-installer.ps1 -Publish       # upload GitHub Release (needs GH_TOKEN)
#   .\build.cmd
param(
    [switch]$SkipSidecar,
    [switch]$Publish,
    [string]$Version = "",
    [string]$PythonVersion = "3.12.8"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Electron = Join-Path $Root "apps\electron"
$RuntimeOut = Join-Path $Electron "build\mango-runtime"
$IconSrc = Join-Path $Electron "src\renderer\src\assets\mango-logo.png"
$IconDstDir = Join-Path $Electron "resources"
$IconDst = Join-Path $IconDstDir "icon.png"
$ReleaseDir = Join-Path $Electron "release"
$CacheDir = Join-Path $Electron "build\cache"

function Assert-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name"
    }
}

function Get-EmbedPythonMajorMinor([string]$FullVersion) {
    $parts = $FullVersion.Split(".")
    return "$($parts[0]).$($parts[1])"
}

function Install-EmbeddablePython([string]$DestDir, [string]$FullVersion) {
    New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null
    $zipName = "python-$FullVersion-embed-amd64.zip"
    $zipPath = Join-Path $CacheDir $zipName
    $url = "https://www.python.org/ftp/python/$FullVersion/$zipName"

    if (-not (Test-Path -LiteralPath $zipPath)) {
        Write-Host "Downloading embeddable Python $FullVersion ..."
        Invoke-WebRequest -Uri $url -OutFile $zipPath
    } else {
        Write-Host "Using cached $zipName"
    }

    if (Test-Path -LiteralPath $DestDir) {
        Remove-Item -LiteralPath $DestDir -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $DestDir | Out-Null
    Expand-Archive -LiteralPath $zipPath -DestinationPath $DestDir -Force

    $mm = Get-EmbedPythonMajorMinor $FullVersion
    $pthName = "python$($mm.Replace('.', ''))._pth"
    $pthPath = Join-Path $DestDir $pthName
    if (-not (Test-Path -LiteralPath $pthPath)) {
        throw "Expected $pthName missing after extract"
    }

    # Enable site-packages so pip-installed deps are importable.
    @(
        "python$($mm.Replace('.', '')).zip"
        "."
        "Lib\site-packages"
        "import site"
    ) | Set-Content -Path $pthPath -Encoding ascii

    $getPip = Join-Path $CacheDir "get-pip.py"
    if (-not (Test-Path -LiteralPath $getPip)) {
        Write-Host "Downloading get-pip.py ..."
        Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip
    }

    $pythonExe = Join-Path $DestDir "python.exe"
    if (-not (Test-Path -LiteralPath $pythonExe)) {
        throw "Embeddable python.exe missing: $pythonExe"
    }

    Write-Host "Bootstrapping pip into embeddable Python ..."
    # Keep native command output off the success stream so callers can capture only the path.
    & $pythonExe $getPip --no-warn-script-location 2>&1 | ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    # Explicitly write nothing else to the pipeline.
    return [string]$pythonExe
}

Write-Host "Mango installer build" -ForegroundColor DarkYellow
Write-Host "  root: $Root"

Assert-Command "node"
Assert-Command "npm"

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

# Packaged config must not ship the builder's absolute GGUF path.
$example = Join-Path $Root "runtime\config.example.yaml"
$configSrc = if (Test-Path -LiteralPath $example) { $example } else { Join-Path $Root "runtime\config.yaml" }
$configDst = Join-Path $RuntimeOut "runtime\config.yaml"
Copy-Item -LiteralPath $configSrc -Destination $configDst -Force
if (Test-Path -LiteralPath $example) {
    Copy-Item -LiteralPath $example -Destination (Join-Path $RuntimeOut "runtime\config.example.yaml") -Force
}
$cfgText = Get-Content -LiteralPath $configDst -Raw
$cfgText = [regex]::Replace($cfgText, "(?m)^(\s*path:\s*).*$", '${1}""')
Set-Content -Path $configDst -Value $cfgText -Encoding utf8

# Marker so packaged tree looks like a Mango root (paths / health checks).
Set-Content -Path (Join-Path $RuntimeOut "agent\python\.mango-runtime") -Value "bundled" -Encoding ascii

if (-not $SkipSidecar) {
    Write-Host "Bundling portable embeddable Python $PythonVersion (not a machine-local venv) ..."
    $pyDir = Join-Path $RuntimeOut "python"
    $py = [string](Install-EmbeddablePython -DestDir $pyDir -FullVersion $PythonVersion)
    if (-not (Test-Path -LiteralPath $py)) {
        throw "Portable python missing after bootstrap: $py"
    }
    Write-Host "  python: $py"

    Write-Host "Installing Mango packages into portable Python (CPU llama-cpp wheel) ..."
    & $py -m pip install --upgrade pip wheel setuptools
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    # Official CPU wheels are on abetlen's index (PyPI often has only sdists for Windows).
    $cpuIndex = "https://abetlen.github.io/llama-cpp-python/whl/cpu"
    Write-Host "  pip install llama-cpp-python (CPU wheel index) ..."
    & $py -m pip install "llama-cpp-python>=0.3.0" --extra-index-url $cpuIndex --prefer-binary
    if ($LASTEXITCODE -ne 0) {
        Write-Host "CPU wheel index failed; trying Vulkan wheel (AMD/Intel/NVIDIA) ..."
        $vulkanIndex = "https://abetlen.github.io/llama-cpp-python/whl/vulkan"
        & $py -m pip install "llama-cpp-python>=0.3.0" --extra-index-url $vulkanIndex --prefer-binary
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Vulkan wheel index failed; trying CUDA wheel index (needs NVIDIA drivers on target) ..."
        $cudaIndex = "https://abetlen.github.io/llama-cpp-python/whl/cu124"
        & $py -m pip install "llama-cpp-python>=0.3.0" --extra-index-url $cudaIndex --prefer-binary
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: could not install llama-cpp-python wheels." -ForegroundColor Red
            Write-Host "Install Visual Studio Build Tools and retry, or pre-install a wheel manually."
            exit $LASTEXITCODE
        }
    }

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
        & $py -m pip install $pkg
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }

    Write-Host "Smoke-testing portable sidecar import ..."
    & $py -c "import llama_cpp, mango_agent, mango_runtime, mango_tools; print('sidecar-ok', getattr(llama_cpp, '__version__', '?'))"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
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
Write-Host "Recipients must set a local GGUF path in Settings (config ships empty)."
