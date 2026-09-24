$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$root = Split-Path $PSScriptRoot -Parent
$replay = Join-Path $root "scripts\drummond_replay01.py"
$compare = Join-Path $root "scripts\mt4_equivalence01.py"
$fixture = Join-Path $root "data\fixtures\XAUUSD"
$base = Join-Path $root "results\latest\equivalence01-selftest"
$replayOut = Join-Path $base "replay"
$self = Join-Path $base "mt4-self"
$passOut = Join-Path $base "pass"
$failOut = Join-Path $base "fail"

if (Test-Path $base) { Remove-Item $base -Recurse -Force }

& python $replay --fixture $fixture --out $replayOut --quote-source h1 --fixed-spread-points 20
if ($LASTEXITCODE -ne 0) { throw "FAIL: equivalence replay generation failed" }

& python $compare make-self-fixture --replay-dir $replayOut --out $self
if ($LASTEXITCODE -ne 0) { throw "FAIL: MT4 self fixture generation failed" }

$watcher = Join-Path $self "DRUMMOND_DEMO02_WATCHER.csv"
$signals = Join-Path $self "DRUMMOND_DEMO02_SIGNALS.csv"

& python $compare compare --replay-dir $replayOut --mt4-watcher $watcher --mt4-signals $signals --out $passOut
if ($LASTEXITCODE -ne 0) { throw "FAIL: comparator rejected exact self fixture" }

$summary = Get-Content (Join-Path $passOut "MT4_EQ01_SUMMARY.json") -Raw | ConvertFrom-Json
if ($summary.status -ne "PASS") { throw "FAIL: self equivalence summary not PASS" }
if ([int]$summary.counts.total_mismatches -ne 0) { throw "FAIL: self equivalence mismatch count not zero" }

$bad = Join-Path $base "DRUMMOND_DEMO02_WATCHER_BAD.csv"
$rows = Import-Csv $watcher -Delimiter ';'
if ($rows.Count -lt 1) { throw "FAIL: empty self watcher" }
$rows[0].REASON = "SELFTEST_MUTATION"
$rows | Export-Csv $bad -Delimiter ';' -NoTypeInformation -Encoding utf8

& python $compare compare --replay-dir $replayOut --mt4-watcher $bad --mt4-signals $signals --out $failOut
if ($LASTEXITCODE -eq 0) { throw "FAIL: comparator did not detect deliberate mismatch" }

$badSummary = Get-Content (Join-Path $failOut "MT4_EQ01_SUMMARY.json") -Raw | ConvertFrom-Json
if ($badSummary.status -ne "FAIL") { throw "FAIL: mutation summary did not report FAIL" }
if ([int]$badSummary.counts.total_mismatches -lt 1) { throw "FAIL: mutation mismatch count not positive" }

Write-Host ""
Write-Host "MT4 EQUIVALENCE 01 HARNESS PASS"
Write-Host ("Replay decisions: " + $summary.counts.replay_audit)
Write-Host ("Replay signals  : " + $summary.counts.replay_signals)
Write-Host "Comparator positive control: PASS"
Write-Host "Comparator negative control: PASS"
exit 0
