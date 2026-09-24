$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$root = Split-Path $PSScriptRoot -Parent
$selection = Join-Path $root "results\latest\equivalence01_hst\HST_SOURCE_SELECTION.json"
$sourceSignals = Join-Path $root "data\mt4_equivalence01\DRUMMOND_DEMO02_SIGNALS.csv"
$analyzer = Join-Path $root "scripts\mt4_executor_capture01.py"
$installer = Join-Path $root "scripts\install-mt4-executor-eq01.ps1"
$work = Join-Path $root "data\mt4_executor_eq01"
$queue = Join-Path $work "DRUMMOND_DEMO02_SIGNALS.csv"

foreach ($p in @($selection,$sourceSignals,$analyzer,$installer)) {
    if (-not (Test-Path $p)) { throw "Missing required file: $p" }
}

& powershell -NoProfile -ExecutionPolicy Bypass -File $installer
if ($LASTEXITCODE -ne 0) {
    throw "Executor installation/compilation is not ready. Follow the exact MetaEditor path printed above, compile once, then rerun this prepare script."
}

$sel = Get-Content $selection -Raw | ConvertFrom-Json
$historyServer = [string]$sel.parent
$historyRoot = Split-Path $historyServer -Parent
$terminalData = Split-Path $historyRoot -Parent
$testerFiles = Join-Path $terminalData "tester\files"

New-Item -ItemType Directory -Force -Path $testerFiles | Out-Null
New-Item -ItemType Directory -Force -Path $work | Out-Null

$start = [DateTimeOffset]::Parse("2026-01-01T00:00:00Z").ToUnixTimeSeconds()
$end = [DateTimeOffset]::Parse("2026-08-27T23:59:59Z").ToUnixTimeSeconds()

& python $analyzer make-queue --source $sourceSignals --out $queue --start $start --end $end
if ($LASTEXITCODE -ne 0) { throw "Failed to build frozen Executor queue" }

Copy-Item $queue (Join-Path $testerFiles "DRUMMOND_DEMO02_SIGNALS.csv") -Force
$oldExec = Join-Path $testerFiles "DRUMMOND_DEMO02_EXECUTION.csv"
if (Test-Path $oldExec) { Remove-Item $oldExec -Force }

Write-Host ""
Write-Host "MT4 EXECUTOR CAPTURE 01 PREPARED"
Write-Host ("MT4 data folder: " + $terminalData)
Write-Host ("Tester files  : " + $testerFiles)
Write-Host "Queue window  : 2026-01-01 -> 2026-08-27"
Write-Host "Expert        : DrummondExecutor_EQ01"
Write-Host "Symbol        : XAUUSD"
Write-Host "Period        : M5"
Write-Host "Model         : Open prices only"
Write-Host "Spread        : 20"
Write-Host "InpRunMode    : hard-fixed TESTER (0) in DrummondExecutor_EQ01"
Write-Host "Tester trading: true (default)"
Write-Host "Inputs file   : not required for run mode; EQ01 is fixed to TESTER by source contract"
