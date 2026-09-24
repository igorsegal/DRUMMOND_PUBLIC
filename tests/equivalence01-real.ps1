$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$root = Split-Path $PSScriptRoot -Parent
$replay = Join-Path $root "scripts\drummond_replay01.py"
$compare = Join-Path $root "scripts\mt4_equivalence01.py"
$fixture = Join-Path $root "data\fixtures\XAUUSD"
$input = Join-Path $root "data\mt4_equivalence01"
$out = Join-Path $root "results\latest\equivalence01"
$replayOut = Join-Path $out "replay"
$cmpOut = Join-Path $out "comparison"
$watcher = Join-Path $input "DRUMMOND_DEMO02_WATCHER.csv"
$signals = Join-Path $input "DRUMMOND_DEMO02_SIGNALS.csv"

if (-not (Test-Path $watcher) -or -not (Test-Path $signals)) {
    throw "MT4 EQUIVALENCE 01 WAITING_FOR_MT4: runtime watcher/signals files are absent"
}

if (Test-Path $out) { Remove-Item $out -Recurse -Force }

& python $replay --fixture $fixture --out $replayOut --quote-source h1 --fixed-spread-points 20
if ($LASTEXITCODE -ne 0) { throw "FAIL: equivalence replay generation failed" }

& python $compare compare --replay-dir $replayOut --mt4-watcher $watcher --mt4-signals $signals --out $cmpOut
$code=$LASTEXITCODE

if (-not (Test-Path (Join-Path $cmpOut "MT4_EQ01_SUMMARY.json"))) {
    throw "FAIL: equivalence comparator produced no summary"
}
$summary = Get-Content (Join-Path $cmpOut "MT4_EQ01_SUMMARY.json") -Raw | ConvertFrom-Json
Write-Host ""
Write-Host ("MT4 EQUIVALENCE 01 REAL STATUS: " + $summary.status)
Write-Host ("Replay audit : " + $summary.counts.replay_audit)
Write-Host ("MT4 audit    : " + $summary.counts.mt4_audit_in_range)
Write-Host ("Replay signal: " + $summary.counts.replay_signals)
Write-Host ("MT4 signal   : " + $summary.counts.mt4_signals_in_range)
Write-Host ("Mismatches   : " + $summary.counts.total_mismatches)

if ($code -ne 0) { exit $code }
Write-Host "MT4 EQUIVALENCE 01 PASS"
