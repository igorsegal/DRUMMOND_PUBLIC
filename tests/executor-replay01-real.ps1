$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$root = Split-Path $PSScriptRoot -Parent
$script = Join-Path $root "scripts\drummond_executor_replay01.py"
$queue = Join-Path $root "data\mt4_executor_eq01\DRUMMOND_DEMO02_SIGNALS.csv"
$execution = Join-Path $root "data\mt4_executor_eq01\DRUMMOND_DEMO02_EXECUTION.csv"
$h1 = Join-Path $root "data\mt4_equivalence01\hst\XAUUSD60.hst"
$out = Join-Path $root "results\latest\executor_replay01"

foreach ($p in @($script,$queue,$execution,$h1)) {
    if (-not (Test-Path $p)) { throw "FAIL: missing Executor Replay 01 input $p" }
}
if (Test-Path $out) { Remove-Item $out -Recurse -Force }

& python $script --queue $queue --execution $execution --h1 $h1 --out $out --spread-points 20
if ($LASTEXITCODE -ne 0) { throw "FAIL: Executor Replay 01 mismatch" }

$summary = Get-Content (Join-Path $out "EXECUTOR_REPLAY01_SUMMARY.json") -Raw | ConvertFrom-Json
if ($summary.status -ne "PASS") { throw "FAIL: Executor Replay 01 summary not PASS" }
if ([int]$summary.counts.queue_signals -ne 29) { throw "FAIL: queue signal count changed" }
if ([int]$summary.counts.deterministic_entry_pass -ne 29) { throw "FAIL: deterministic entry gates not 29/29" }
if ([int]$summary.counts.exact_entry_price -ne 29) { throw "FAIL: entry price not 29/29 exact" }
if ([int]$summary.counts.opened -ne 29) { throw "FAIL: opened count not 29" }
if ([int]$summary.counts.trail_rows -ne 49) { throw "FAIL: trail row count not 49" }
if ([int]$summary.counts.exact_trail_candidate -ne 49) { throw "FAIL: trail candidate not 49/49 exact" }
if ([int]$summary.counts.mismatches -ne 0) { throw "FAIL: Executor Replay 01 mismatches detected" }

Write-Host ""
Write-Host "DRUMMOND EXECUTOR REPLAY 01 CONTRACT PASS"
