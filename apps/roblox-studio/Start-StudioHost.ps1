# Start mango-studio-host (invisible-friendly console). Requires Python with Mango packages.

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $here "..\..")).Path
$hostPy = Join-Path $here "host\python"

$env:MANGO_REPO_ROOT = $repoRoot
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONNOUSERSITE = "1"

$parts = @(
    (Join-Path $repoRoot "agent\python"),
    (Join-Path $repoRoot "tools\python"),
    (Join-Path $repoRoot "runtime\python"),
    (Join-Path $repoRoot "context\python"),
    (Join-Path $repoRoot "cot\python"),
    (Join-Path $repoRoot "epistemic\python"),
    (Join-Path $repoRoot "codeintel\python"),
    (Join-Path $repoRoot "verification\python"),
    $hostPy
)
$env:PYTHONPATH = ($parts -join ";")
$env:MANGO_PROMPTS_DIR = Join-Path $repoRoot "prompts"

$pythonCandidates = @(
    (Join-Path $repoRoot "python\python.exe"),
    (Join-Path $repoRoot "agent\python\.venv\Scripts\python.exe"),
    (Join-Path $repoRoot ".venv\Scripts\python.exe"),
    "python"
)
$python = $null
foreach ($c in $pythonCandidates) {
    if ($c -eq "python") { $python = $c; break }
    if (Test-Path $c) { $python = $c; break }
}

$wait = $args -contains "-WaitForStudio"
$portArg = @("--port", "17880")
if ($wait) { $portArg += "--wait-for-studio" }

Write-Host "Repo: $repoRoot"
Write-Host "Python: $python"
Write-Host "Listening on http://127.0.0.1:17880 …"
Set-Location $repoRoot
& $python -m mango_studio_host @portArg
