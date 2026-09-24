$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$root = Split-Path $PSScriptRoot -Parent
$script = Join-Path $root "scripts\executor_lifecycle02.py"
$base = Join-Path $root "data\mt4_lifecycle02"
$queue = Join-Path $base "DRUMMOND_DEMO02_SIGNALS.csv"
$execution = Join-Path $base "DRUMMOND_DEMO02_EXECUTION.csv"
$lifecycle = Join-Path $base "DRUMMOND_DEMO02_LIFECYCLE.csv"
$m5 = Join-Path $base "hst\XAUUSD5.hst"
$out = Join-Path $root "results\latest\executor_lifecycle02_ci"

foreach($p in @($script,$queue,$execution,$lifecycle,$m5)){
  if(-not(Test-Path $p)){throw "FAIL: missing Lifecycle 02 evidence $p"}
}
if(Test-Path $out){Remove-Item $out -Recurse -Force}

& python $script analyze --queue $queue --execution $execution --lifecycle $lifecycle --m5 $m5 --out $out --spread-points 20
if($LASTEXITCODE -ne 0){throw "FAIL: Executor Lifecycle 02 mismatch"}

$summary=Get-Content (Join-Path $out "EXECUTOR_LIFECYCLE02_SUMMARY.json") -Raw | ConvertFrom-Json
if($summary.status -ne "PASS"){throw "FAIL: Lifecycle 02 summary not PASS"}
if([int]$summary.counts.opened_tickets -ne 29){throw "FAIL: opened ticket count changed"}
if([int]$summary.counts.mismatches -ne 0){throw "FAIL: Lifecycle 02 mismatches detected"}

Write-Host ""
Write-Host "EXECUTOR LIFECYCLE 02 REAL PASS"
