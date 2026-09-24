$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$root = Split-Path $PSScriptRoot -Parent
$packer = Join-Path $root "scripts\data_bridge_pack02.py"
$verify = Join-Path $root "scripts\data_bridge_verify02.py"
$factory = Join-Path $root "scripts\cloud_factory01.py"
$aggregate = Join-Path $root "scripts\cloud_factory_aggregate02.py"
$replay = Join-Path $root "scripts\drummond_replay01.py"
$fixture = Join-Path $root "data\fixtures\XAUUSD"
$work = Join-Path $root "results\latest\data_bridge02_contract"
$raw = Join-Path $work "raw"
$packageRoot = Join-Path $work "package"
$verified = Join-Path $work "verified"
$factoryOut = Join-Path $work "factory"
$artifactRoot = Join-Path $work "artifacts"
$aggregateOut = Join-Path $work "aggregate"
$anchorOut = Join-Path $work "anchor"
$config = Join-Path $work "config.json"

foreach($p in @($packer,$verify,$factory,$aggregate,$replay,$fixture)){
  if(-not(Test-Path $p)){throw "FAIL: missing $p"}
}
if(Test-Path $work){Remove-Item $work -Recurse -Force}
$xau = Join-Path $raw "XAUUSD"
New-Item -ItemType Directory -Force -Path $xau | Out-Null
foreach($tf in @("M5","H1","H4")){
  Copy-Item (Join-Path $fixture ("XAUUSD_" + $tf + ".bin")) (Join-Path $xau ("XAUUSD_" + $tf + ".bin"))
}

@'
{
  "mode": "discover",
  "max_ready_symbols": 1,
  "include_incomplete_symbols": 0,
  "always_include": ["XAUUSD"],
  "target_shard_mb": 1
}
'@ | Set-Content $config -Encoding UTF8

& python $packer --canonical-root $raw --out-root $packageRoot --config $config
if($LASTEXITCODE -ne 0){throw "FAIL: Scale 02 packer"}

$latest = Get-Content (Join-Path $packageRoot "LATEST.json") -Raw | ConvertFrom-Json
$datasetDir = [string]$latest.dataset_dir
$datasetId = [string]$latest.dataset_id
$manifest = Get-Content (Join-Path $datasetDir "DATASET_MANIFEST.json") -Raw | ConvertFrom-Json

if($manifest.schema -ne "DRUMMOND_DATA_BRIDGE_02"){throw "FAIL: Scale 02 schema"}
if($manifest.policy.sharding -ne "SYMBOL_ATOMIC"){throw "FAIL: Scale 02 sharding policy"}
if($manifest.selection.mode -ne "discover"){throw "FAIL: discover mode not preserved"}
if($manifest.symbol_status.Count -ne 1){throw "FAIL: expected one discovered symbol"}
if($manifest.symbol_status[0].symbol -ne "XAUUSD" -or $manifest.symbol_status[0].status -ne "READY"){throw "FAIL: XAUUSD discovery/status"}
if($manifest.files.Count -ne 3){throw "FAIL: XAUUSD file count"}
if($manifest.shards.Count -ne 1){throw "FAIL: symbol-atomic oversize group must remain one shard"}
if([int]$manifest.shards[0].symbol_count -ne 1){throw "FAIL: shard symbol count"}
if([int]$manifest.shards[0].file_count -ne 3){throw "FAIL: shard file count"}
if(-not [bool]$manifest.shards[0].oversize_symbol_group){throw "FAIL: oversize atomic group not flagged"}
$assigned=@($manifest.files | ForEach-Object { $_.shard } | Select-Object -Unique)
if($assigned.Count -ne 1){throw "FAIL: XAUUSD was split across shards"}

& python $verify --package-dir $datasetDir --out-root (Join-Path $work "manifest_check") --expected-dataset-id $datasetId --manifest-only
if($LASTEXITCODE -ne 0){throw "FAIL: Scale 02 manifest verifier"}

$shard=[string]$manifest.shards[0].name
& python $verify --package-dir $datasetDir --out-root $verified --expected-dataset-id $datasetId --shard $shard
if($LASTEXITCODE -ne 0){throw "FAIL: Scale 02 shard verifier"}

& python $factory --data-root $verified --out $factoryOut
if($LASTEXITCODE -ne 0){throw "FAIL: Factory on Scale 02 shard"}

$artifact = Join-Path $artifactRoot ("drummond-db02-" + $shard)
New-Item -ItemType Directory -Force -Path $artifact | Out-Null
Copy-Item $factoryOut (Join-Path $artifact "factory") -Recurse -Force

& python $aggregate --artifact-root $artifactRoot --manifest (Join-Path $datasetDir "DATASET_MANIFEST.json") --out $aggregateOut
if($LASTEXITCODE -ne 0){throw "FAIL: Scale 02 aggregate"}

$s = Get-Content (Join-Path $aggregateOut "FACTORY02_SUMMARY.json") -Raw | ConvertFrom-Json
if($s.status -ne "PASS"){throw "FAIL: aggregate status"}
if([int]$s.counts.processed -ne 1){throw "FAIL: aggregate processed"}
if([int]$s.counts.errors -ne 0){throw "FAIL: aggregate errors"}
if([int]$s.counts.signals -ne 509){throw "FAIL: aggregate XAUUSD signal count"}
if([int]$s.counts.shard_results -ne 1 -or [int]$s.counts.shards_expected -ne 1){throw "FAIL: aggregate shard coverage"}

& python $replay --fixture (Join-Path $verified "XAUUSD") --symbol XAUUSD --out $anchorOut --end-time 1787731200
if($LASTEXITCODE -ne 0){throw "FAIL: Scale 02 frozen anchor"}
$a = Get-Content (Join-Path $anchorOut "XAUUSD_REPLAY_SUMMARY.json") -Raw | ConvertFrom-Json
if([int]$a.counts.signals -ne 509){throw "FAIL: frozen anchor count"}
if($a.signal_sha256 -ne "8411a05a1ca5a4a771c74e3e87d37d2562b370681258ec4b246fa3818f29cd40"){throw "FAIL: frozen anchor hash"}

Write-Host ""
Write-Host "CLOUD DATA BRIDGE SCALE 02 CONTRACT PASS"
Write-Host ("Dataset : " + $datasetId)
Write-Host ("Shard   : " + $shard)
Write-Host ("Signals : " + $s.counts.signals)
