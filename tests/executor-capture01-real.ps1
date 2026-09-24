$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$root = Split-Path $PSScriptRoot -Parent
$analyzer = Join-Path $root "scripts\mt4_executor_capture01.py"
$queue = Join-Path $root "data\mt4_executor_eq01\DRUMMOND_DEMO02_SIGNALS.csv"
$execution = Join-Path $root "data\mt4_executor_eq01\DRUMMOND_DEMO02_EXECUTION.csv"
$out = Join-Path $root "results\latest\executor_capture01_ci"

foreach ($p in @($analyzer,$queue,$execution)) {
    if (-not (Test-Path $p)) { throw "FAIL: missing Executor capture input $p" }
}
if (Test-Path $out) { Remove-Item $out -Recurse -Force }

& python $analyzer analyze --queue $queue --execution $execution --out $out --max-age-minutes 15
if ($LASTEXITCODE -ne 0) { throw "FAIL: MT4 Executor capture architecture violation" }

Write-Host ""
Write-Host "MT4 EXECUTOR CAPTURE 01 REAL PASS"
