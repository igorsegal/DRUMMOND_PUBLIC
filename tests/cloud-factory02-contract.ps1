$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$root = Split-Path $PSScriptRoot -Parent
$script = Join-Path $root "scripts\cloud_factory02.py"
$data = Join-Path $root "data\fixtures"
$out = Join-Path $root "results\latest\factory02"

if(-not(Test-Path $script)){throw "FAIL: missing Factory 02 script"}
if(Test-Path $out){Remove-Item $out -Recurse -Force}

& python $script selftest
if($LASTEXITCODE -ne 0){throw "FAIL: Factory 02 selftest"}

& python $script run --data-root $data --out $out --symbols XAUUSD
if($LASTEXITCODE -ne 0){throw "FAIL: Factory 02 XAUUSD run"}

$summary = Get-Content (Join-Path $out "FACTORY02_SUMMARY.json") -Raw | ConvertFrom-Json
if($summary.status -ne "PASS"){throw "FAIL: Factory 02 summary not PASS"}
if([int]$summary.counts.processed -ne 1){throw "FAIL: processed count"}
if([int]$summary.counts.errors -ne 0){throw "FAIL: errors present"}
if([int]$summary.counts.signals -ne 509){throw "FAIL: signal count drift"}
$total=[int]$summary.counts.TP+[int]$summary.counts.SL+[int]$summary.counts.AMBIGUOUS_SAME_M5+[int]$summary.counts.OPEN_AT_DATA_END
if($total -ne 509){throw "FAIL: lifecycle outcome conservation"}
if([int]$summary.counts.trail_updates -le 0){throw "FAIL: expected structural trail updates"}

$rows = Import-Csv (Join-Path $out "FACTORY02_SYMBOLS.csv") -Delimiter ';'
$x = $rows | Where-Object { $_.SYMBOL -eq "XAUUSD" }
if($null -eq $x){throw "FAIL: XAUUSD row missing"}
if($x.STATUS -ne "PROCESSED"){throw "FAIL: XAUUSD not processed"}
if($x.LIFECYCLE_SHA256 -ne "379155ff8f4f54a1ea0d9c156776f5598acd7a9b2cd379c540f67cb0c7d8d50d"){
  throw "FAIL: XAUUSD lifecycle hash drift"
}
if([int]$summary.counts.TP -ne 165){throw "FAIL: XAUUSD Factory02 TP drift"}
if([int]$summary.counts.SL -ne 342){throw "FAIL: XAUUSD Factory02 SL drift"}
if([int]$summary.counts.AMBIGUOUS_SAME_M5 -ne 2){throw "FAIL: XAUUSD Factory02 ambiguous drift"}
if([int]$summary.counts.trail_updates -ne 733){throw "FAIL: XAUUSD Factory02 trail count drift"}

Write-Host ""
Write-Host "CLOUD FACTORY 02 CONTRACT PASS"
Write-Host ("Signals      : " + $summary.counts.signals)
Write-Host ("TP/SL/A/O    : " + $summary.counts.TP + "/" + $summary.counts.SL + "/" + $summary.counts.AMBIGUOUS_SAME_M5 + "/" + $summary.counts.OPEN_AT_DATA_END)
Write-Host ("Trail updates: " + $summary.counts.trail_updates)
Write-Host ("Lifecycle SHA: " + $x.LIFECYCLE_SHA256)
