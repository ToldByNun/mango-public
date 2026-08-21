# Mango SWE-bench Lite baseline (10 curated instances)
# Usage:
#   .\scripts\run_swebench_baseline.ps1              # inference only
#   .\scripts\run_swebench_baseline.ps1 -Evaluate  # + official Docker harness
#   .\scripts\run_swebench_baseline.ps1 -SaveReference
#   .\scripts\run_swebench_baseline.ps1 -Evaluate -Compare

param(
    [switch]$Evaluate,
    [switch]$SaveReference,
    [switch]$Compare,
    [string]$OutputDir = "swebench_reports/baseline",
    [string]$Config,
    [int]$EvalWorkers = 2
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$args = @(
    "-m", "mango_agent.benchmark.swebench",
    "--baseline",
    "--output-dir", $OutputDir
)

if ($Config) { $args += @("--baseline-config", $Config) }
if ($Evaluate) { $args += "--evaluate"; $args += @("--eval-workers", "$EvalWorkers") }
if ($SaveReference) { $args += "--save-reference" }
if ($Compare) {
    $ref = Join-Path $OutputDir "reference.json"
    if (-not (Test-Path $ref)) {
        Write-Error "Missing reference report: $ref (run with -SaveReference first)"
    }
    $args += @("--compare", $ref)
}

python @args
