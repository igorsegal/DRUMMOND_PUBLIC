$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$root = Split-Path $PSScriptRoot -Parent
$bridge = Join-Path $root "scripts\mt4_hst_replay01.py"
$compare = Join-Path $root "scripts\mt4_equivalence01.py"
$h1 = Join-Path $root "data\mt4_equivalence01\hst\XAUUSD60.hst"
$h4 = Join-Path $root "data\mt4_equivalence01\hst\XAUUSD240.hst"
$watcher = Join-Path $root "data\mt4_equivalence01\DRUMMOND_DEMO02_WATCHER.csv"
$signals = Join-Path $root "data\mt4_equivalence01\DRUMMOND_DEMO02_SIGNALS.csv"
$out = Join-Path $root "results\latest\equivalence01_hst_ci"
$replay = Join-Path $out "replay"
$cmp = Join-Path $out "comparison"

foreach ($p in @($bridge,$compare,$h1,$h4,$watcher,$signals)) {
    if (-not (Test-Path $p)) { throw "FAIL: missing required HST equivalence input $p" }
}
if (Test-Path $out) { Remove-Item $out -Recurse -Force }

& python $bridge replay --h1 $h1 --h4 $h4 --watcher $watcher --out $replay --spread-points 20
if ($LASTEXITCODE -ne 0) { throw "FAIL: HST replay mapping failed" }

$audit = Join-Path $replay "XAUUSD_HST_REPLAY_AUDIT.csv"
$replaySignals = Join-Path $replay "XAUUSD_HST_REPLAY_SIGNALS.csv"
& python $compare compare --replay-dir $replay --replay-audit $audit --replay-signals $replaySignals --mt4-watcher $watcher --mt4-signals $signals --out $cmp
if ($LASTEXITCODE -ne 0) { throw "FAIL: MT4 HST logic equivalence mismatch" }

Write-Host ""
Write-Host "MT4 HST EQUIVALENCE 01 PASS"
