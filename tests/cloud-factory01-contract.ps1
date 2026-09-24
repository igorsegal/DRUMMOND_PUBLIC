$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$root = Split-Path $PSScriptRoot -Parent
$factory = Join-Path $root "scripts\cloud_factory01.py"
$src = Join-Path $root "data\fixtures\XAUUSD"
$input = Join-Path $root "results\latest\factory01_selftest_input"
$out = Join-Path $root "results\latest\factory01"

if (Test-Path $input) { Remove-Item $input -Recurse -Force }
if (Test-Path $out) { Remove-Item $out -Recurse -Force }

$xau = Join-Path $input "XAUUSD"
$nom5 = Join-Path $input "NO_M5"
New-Item -ItemType Directory -Force -Path $xau,$nom5 | Out-Null

foreach($tf in @("M5","H1","H4")) {
    Copy-Item (Join-Path $src ("XAUUSD_" + $tf + ".bin")) (Join-Path $xau ("XAUUSD_" + $tf + ".bin"))
}
Copy-Item (Join-Path $src "XAUUSD_H1.bin") (Join-Path $nom5 "NO_M5_H1.bin")
Copy-Item (Join-Path $src "XAUUSD_H4.bin") (Join-Path $nom5 "NO_M5_H4.bin")

& python $factory --data-root $input --out $out
if ($LASTEXITCODE -ne 0) { throw "FAIL: CLOUD FACTORY 01 returned $LASTEXITCODE" }

$summary = Get-Content (Join-Path $out "FACTORY01_SUMMARY.json") -Raw | ConvertFrom-Json
if ($summary.status -ne "PASS") { throw "FAIL: Factory 01 status not PASS" }
if ([int]$summary.counts.processed -ne 1) { throw "FAIL: processed count must be 1" }
if ([int]$summary.counts.skip_no_m5 -ne 1) { throw "FAIL: SKIP_NO_M5 contract failed" }
if ([int]$summary.counts.errors -ne 0) { throw "FAIL: Factory 01 has errors" }
if ([int]$summary.counts.signals -ne 509) { throw "FAIL: XAUUSD signal count drifted" }
if ([int]$summary.counts.decisions -lt 49000) { throw "FAIL: too few XAUUSD decisions" }

$rows = Import-Csv (Join-Path $out "FACTORY01_SYMBOLS.csv") -Delimiter ';'
$x = $rows | Where-Object { $_.SYMBOL -eq "XAUUSD" }
$m = $rows | Where-Object { $_.SYMBOL -eq "NO_M5" }
if ($x.STATUS -ne "PROCESSED") { throw "FAIL: XAUUSD not processed" }
if ($x.SIGNAL_SHA256 -ne "8411a05a1ca5a4a771c74e3e87d37d2562b370681258ec4b246fa3818f29cd40") { throw "FAIL: XAUUSD signal hash drifted" }
if ($m.STATUS -ne "SKIP_NO_M5") { throw "FAIL: NO_M5 was not skipped correctly" }

Write-Host ""
Write-Host "CLOUD FACTORY 01 CONTRACT PASS"
Write-Host ("Processed : " + $summary.counts.processed)
Write-Host ("Skip M5   : " + $summary.counts.skip_no_m5)
Write-Host ("Signals   : " + $summary.counts.signals)
