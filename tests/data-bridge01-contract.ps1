$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$root = Split-Path $PSScriptRoot -Parent
$packer = Join-Path $root "scripts\data_bridge_pack01.py"
$verify = Join-Path $root "scripts\data_bridge_verify01.py"
$factory = Join-Path $root "scripts\cloud_factory01.py"
$replay = Join-Path $root "scripts\drummond_replay01.py"
$fixture = Join-Path $root "data\fixtures\XAUUSD"
$work = Join-Path $root "results\latest\data_bridge01_contract"
$raw = Join-Path $work "raw"
$packageRoot = Join-Path $work "package"
$verified = Join-Path $work "verified"
$factoryOut = Join-Path $work "factory"
$anchorOut = Join-Path $work "anchor"

foreach($p in @($packer,$verify,$factory,$replay,$fixture)){
  if(-not(Test-Path $p)){throw "FAIL: missing $p"}
}

if(Test-Path $work){Remove-Item $work -Recurse -Force}
$xau = Join-Path $raw "XAUUSD"
New-Item -ItemType Directory -Force -Path $xau | Out-Null
foreach($tf in @("M5","H1","H4")){
  Copy-Item (Join-Path $fixture ("XAUUSD_" + $tf + ".bin")) (Join-Path $xau ("XAUUSD_" + $tf + ".bin"))
}

& python $packer --canonical-root $raw --out-root $packageRoot --symbols XAUUSD --target-shard-mb 20
if($LASTEXITCODE -ne 0){throw "FAIL: Data Bridge packer"}

$latest = Get-Content (Join-Path $packageRoot "LATEST.json") -Raw | ConvertFrom-Json
$datasetDir = [string]$latest.dataset_dir
$datasetId = [string]$latest.dataset_id
$manifest = Get-Content (Join-Path $datasetDir "DATASET_MANIFEST.json") -Raw | ConvertFrom-Json

if($manifest.schema -ne "DRUMMOND_DATA_BRIDGE_01"){throw "FAIL: manifest schema"}
if($manifest.dataset_id -ne $datasetId){throw "FAIL: dataset id disagreement"}
if($manifest.files.Count -ne 3){throw "FAIL: expected 3 XAUUSD files"}
if($manifest.symbol_status.Count -ne 1){throw "FAIL: expected 1 symbol status"}
if($manifest.symbol_status[0].status -ne "READY"){throw "FAIL: XAUUSD must be READY"}
if($manifest.shards.Count -lt 1){throw "FAIL: no shards created"}

& python $verify --package-dir $datasetDir --out-root $verified --expected-dataset-id $datasetId
if($LASTEXITCODE -ne 0){throw "FAIL: Data Bridge verifier"}

$verifiedMeta = Get-Content (Join-Path $verified "VERIFIED_DATASET.json") -Raw | ConvertFrom-Json
if($verifiedMeta.dataset_id -ne $datasetId){throw "FAIL: verified dataset id"}
if([int]$verifiedMeta.verified_files -ne 3){throw "FAIL: verified file count"}

foreach($tf in @("M5","H1","H4")){
  $p = Join-Path $verified ("XAUUSD\XAUUSD_" + $tf + ".bin")
  if(-not(Test-Path $p)){throw "FAIL: verified file missing $p"}
}

& python $factory --data-root $verified --out $factoryOut
if($LASTEXITCODE -ne 0){throw "FAIL: Factory on verified Data Bridge dataset"}

$summary = Get-Content (Join-Path $factoryOut "FACTORY01_SUMMARY.json") -Raw | ConvertFrom-Json
if($summary.status -ne "PASS"){throw "FAIL: Factory status"}
if([int]$summary.counts.processed -ne 1){throw "FAIL: processed count"}
if([int]$summary.counts.errors -ne 0){throw "FAIL: Factory errors"}
if([int]$summary.counts.signals -ne 509){throw "FAIL: XAUUSD signal count drift"}

$rows = Import-Csv (Join-Path $factoryOut "FACTORY01_SYMBOLS.csv") -Delimiter ';'
$x = $rows | Where-Object { $_.SYMBOL -eq "XAUUSD" }
if($x.SIGNAL_SHA256 -ne "8411a05a1ca5a4a771c74e3e87d37d2562b370681258ec4b246fa3818f29cd40"){
  throw "FAIL: XAUUSD signal hash drift"
}

& python $replay --fixture (Join-Path $verified "XAUUSD") --symbol XAUUSD --out $anchorOut --end-time 1787731200
if($LASTEXITCODE -ne 0){throw "FAIL: frozen XAUUSD anchor replay"}
$anchor = Get-Content (Join-Path $anchorOut "XAUUSD_REPLAY_SUMMARY.json") -Raw | ConvertFrom-Json
if([int]$anchor.common_period.end -ne 1787731200){throw "FAIL: frozen anchor end time"}
if([int]$anchor.counts.signals -ne 509){throw "FAIL: frozen anchor signals"}
if($anchor.signal_sha256 -ne "8411a05a1ca5a4a771c74e3e87d37d2562b370681258ec4b246fa3818f29cd40"){
  throw "FAIL: frozen anchor hash"
}

Write-Host ""
Write-Host "CLOUD DATA BRIDGE 01 CONTRACT PASS"
Write-Host ("Dataset : " + $datasetId)
Write-Host ("Shards  : " + $manifest.shards.Count)
Write-Host ("Files   : " + $verifiedMeta.verified_files)
Write-Host ("Signals : " + $summary.counts.signals)
Write-Host ("Anchor end: " + $anchor.common_period.end)
