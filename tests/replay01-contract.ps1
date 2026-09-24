$ErrorActionPreference = "Stop"

$root = Split-Path $PSScriptRoot -Parent
$script = Join-Path $root "scripts\drummond_replay01.py"
$fixture = Join-Path $root "data\fixtures\XAUUSD"
$out = Join-Path $root "results\latest\replay01"

if (-not (Test-Path $script)) { throw "FAIL: missing scripts/drummond_replay01.py" }

foreach ($tf in @("M5","H1","H4")) {
    $p = Join-Path $fixture ("XAUUSD_" + $tf + ".bin")
    if (-not (Test-Path $p)) { throw "FAIL: missing replay fixture $p" }
    if ((Get-Item $p).Length -le 0) { throw "FAIL: empty replay fixture $p" }
}

if (Test-Path $out) { Remove-Item $out -Recurse -Force }

& python $script --fixture $fixture --out $out
if ($LASTEXITCODE -ne 0) { throw "FAIL: DRUMMOND REPLAY 01 returned $LASTEXITCODE" }

$required = @(
    "XAUUSD_REPLAY_AUDIT.csv",
    "XAUUSD_REPLAY_SIGNALS.csv",
    "XAUUSD_REPLAY_OUTCOMES.csv",
    "XAUUSD_REPLAY_SUMMARY.json",
    "XAUUSD_REPLAY_SUMMARY.txt"
)

foreach ($name in $required) {
    $p = Join-Path $out $name
    if (-not (Test-Path $p)) { throw "FAIL: missing replay output $name" }
    if ((Get-Item $p).Length -le 0) { throw "FAIL: empty replay output $name" }
    Write-Host "[OK] replay output: $name"
}

$summary = Get-Content (Join-Path $out "XAUUSD_REPLAY_SUMMARY.json") -Raw | ConvertFrom-Json

if ($summary.status -ne "PASS") { throw "FAIL: replay summary status is not PASS" }
if ($summary.symbol -ne "XAUUSD") { throw "FAIL: replay symbol mismatch" }
if ([int]$summary.contract.fixed_header_bytes -ne 60) { throw "FAIL: XFBAR fixed header must be 60 bytes" }
if ([int]$summary.contract.record_size -ne 60) { throw "FAIL: XFBAR record size must be 60 bytes" }
if ([int]$summary.parameters.execution_tf_seconds -ne 300) { throw "FAIL: M5 period mismatch" }
if ([int]$summary.parameters.decision_tf_seconds -ne 3600) { throw "FAIL: H1 period mismatch" }
if ([int]$summary.parameters.htp_tf_seconds -ne 14400) { throw "FAIL: H4 period mismatch" }

if ([int]$summary.data.M5.bar_count -lt 1000) { throw "FAIL: too few M5 bars" }
if ([int]$summary.data.H1.bar_count -lt 1000) { throw "FAIL: too few H1 bars" }
if ([int]$summary.data.H4.bar_count -lt 1000) { throw "FAIL: too few H4 bars" }
if ([int]$summary.counts.decisions -lt 1000) { throw "FAIL: too few replay decisions" }
if ([int]$summary.counts.future_guard_violations -ne 0) { throw "FAIL: future guard violation" }
if ([int]$summary.alignment.H1_from_M5.checked -le 0) { throw "FAIL: no H1/M5 alignment checks" }
if ([int]$summary.alignment.H4_from_M5.checked -le 0) { throw "FAIL: no H4/M5 alignment checks" }
if ($summary.signal_sha256 -notmatch '^[0-9a-f]{64}$') { throw "FAIL: invalid signal SHA256" }

Write-Host ""
Write-Host "DRUMMOND REPLAY 01 CONTRACT PASS"
Write-Host ("Decisions: " + $summary.counts.decisions)
Write-Host ("Signals  : " + $summary.counts.signals)
Write-Host ("Hash     : " + $summary.signal_sha256)
