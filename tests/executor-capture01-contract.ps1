$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$root = Split-Path $PSScriptRoot -Parent
$script = Join-Path $root "scripts\mt4_executor_capture01.py"
$tmp = Join-Path $root "results\latest\executor_capture01_selftest"

if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }

& python $script selftest --tmp $tmp
if ($LASTEXITCODE -ne 0) { throw "FAIL: MT4 Executor capture selftest failed" }

$summary = Get-Content (Join-Path $tmp "out\MT4_EXEC_EQ01_SUMMARY.json") -Raw | ConvertFrom-Json
if ($summary.status -ne "PASS") { throw "FAIL: Executor capture selftest summary not PASS" }
if ([int]$summary.queue_signals -ne 3) { throw "FAIL: selftest queue count mismatch" }
if ([int]$summary.terminal.opened -ne 1) { throw "FAIL: selftest opened count mismatch" }
if ([int]$summary.terminal.rejected -ne 1) { throw "FAIL: selftest rejected count mismatch" }
if ([int]$summary.terminal.blocked -ne 1) { throw "FAIL: selftest blocked count mismatch" }
if ([int]$summary.violation_count -ne 0) { throw "FAIL: selftest violations detected" }

Write-Host ""
Write-Host "MT4 EXECUTOR CAPTURE 01 HARNESS PASS"
