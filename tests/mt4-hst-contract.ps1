$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$script = Join-Path $root "scripts\mt4_hst_replay01.py"

if (-not (Test-Path $script)) { throw "FAIL: missing scripts/mt4_hst_replay01.py" }

& python $script selftest
if ($LASTEXITCODE -ne 0) { throw "FAIL: MT4 HST bridge selftest failed" }

Write-Host ""
Write-Host "MT4 HST BRIDGE CONTRACT PASS"
