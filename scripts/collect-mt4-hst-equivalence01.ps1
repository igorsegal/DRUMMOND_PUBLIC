param([switch]$Push)
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$root = Split-Path $PSScriptRoot -Parent
$terminalRoot = Join-Path $env:APPDATA "MetaQuotes\Terminal"
$watcher = Join-Path $root "data\mt4_equivalence01\DRUMMOND_DEMO02_WATCHER.csv"
$signals = Join-Path $root "data\mt4_equivalence01\DRUMMOND_DEMO02_SIGNALS.csv"
$bridge = Join-Path $root "scripts\mt4_hst_replay01.py"
$compare = Join-Path $root "scripts\mt4_equivalence01.py"
$hstDir = Join-Path $root "data\mt4_equivalence01\hst"
$out = Join-Path $root "results\latest\equivalence01_hst"
$replayOut = Join-Path $out "replay"
$cmpOut = Join-Path $out "comparison"

if (-not (Test-Path $terminalRoot)) { throw "MetaQuotes terminal root not found" }
if (-not (Test-Path $watcher)) { throw "Missing watcher evidence" }
if (-not (Test-Path $signals)) { throw "Missing signal evidence" }

$raw = & python $bridge find --terminal-root $terminalRoot --symbol XAUUSD --watcher $watcher
if ($LASTEXITCODE -ne 0) { throw "FAIL: no matching XAUUSD H1/H4 HST pair" }
$pick = ($raw -join [Environment]::NewLine) | ConvertFrom-Json

New-Item -ItemType Directory -Force -Path $hstDir | Out-Null
$h1Dest = Join-Path $hstDir "XAUUSD60.hst"
$h4Dest = Join-Path $hstDir "XAUUSD240.hst"
Copy-Item $pick.h1 $h1Dest -Force
Copy-Item $pick.h4 $h4Dest -Force

if (Test-Path $out) { Remove-Item $out -Recurse -Force }
& python $bridge replay --h1 $h1Dest --h4 $h4Dest --watcher $watcher --out $replayOut --spread-points 20
$replayCode = $LASTEXITCODE

$audit = Join-Path $replayOut "XAUUSD_HST_REPLAY_AUDIT.csv"
$replaySignals = Join-Path $replayOut "XAUUSD_HST_REPLAY_SIGNALS.csv"
& python $compare compare --replay-dir $replayOut --replay-audit $audit --replay-signals $replaySignals --mt4-watcher $watcher --mt4-signals $signals --out $cmpOut
$compareCode = $LASTEXITCODE

$pick | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $out "HST_SOURCE_SELECTION.json") -Encoding utf8

Write-Host ("Selected HST folder: " + $pick.parent)
Write-Host ("Decision overlap: " + $pick.decision_overlap)
Write-Host ("Entry sample MAE: " + $pick.entry_mae)

if ($compareCode -eq 0 -and $replayCode -eq 0) {
    Write-Host "MT4 HST EQUIVALENCE 01 PASS"
    exit 0
}
Write-Host "MT4 HST EQUIVALENCE 01 produced a deterministic mismatch report."
exit 2
