$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$root = Split-Path $PSScriptRoot -Parent
$script = Join-Path $root "scripts\executor_lifecycle02.py"
$tmp = Join-Path $root "results\latest\executor_lifecycle02_selftest"

if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
& python $script selftest
if ($LASTEXITCODE -ne 0) { throw "FAIL: Executor Lifecycle 02 selftest failed" }

Write-Host ""
Write-Host "EXECUTOR LIFECYCLE 02 HARNESS PASS"
