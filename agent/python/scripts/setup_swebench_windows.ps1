# Install WSL2 + Docker Desktop for official SWE-bench harness evaluation.
# Run as Administrator. PowerShell execution policy: use setup_swebench_windows.cmd

$ErrorActionPreference = "Continue"

Write-Host "==> Checking WSL..."
$wslOk = $false
try {
    $null = & wsl.exe --status 2>$null
    if ($LASTEXITCODE -eq 0) { $wslOk = $true }
} catch {
    $wslOk = $false
}

if (-not $wslOk) {
    Write-Host "Installing WSL2 (Windows may reboot)..."
    $ErrorActionPreference = "Stop"
    & wsl.exe --install
    $code = $LASTEXITCODE
    Write-Host ""
    Write-Host "WSL install started (exit $code)."
    Write-Host "Reboot Windows if prompted, then re-run this script to install Docker Desktop."
    exit 3010
}

Write-Host "WSL is present. Installing Docker Desktop via winget..."
$ErrorActionPreference = "Stop"
winget install Docker.DockerDesktop `
    --accept-package-agreements `
    --accept-source-agreements `
    --disable-interactivity

Write-Host ""
Write-Host "Done. Start Docker Desktop from the Start menu, wait until it is running,"
Write-Host "then run: powershell -ExecutionPolicy Bypass -File .\scripts\run_swebench_baseline.ps1 -Evaluate"
