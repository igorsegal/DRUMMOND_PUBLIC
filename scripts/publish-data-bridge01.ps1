$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$root = Split-Path $PSScriptRoot -Parent
$canonical = "D:\AHexaTrader\1DataFiles\raw"
$config = Join-Path $root "config\DATA_BRIDGE01.json"
$packer = Join-Path $root "scripts\data_bridge_pack01.py"
$outRoot = Join-Path $root "bridge_out"
$gh = "D:\GitHub CLI\gh.exe"
$repo = "igorsegal/DRUMMOND_CLOUD"

foreach($p in @($canonical,$config,$packer,$gh)){
  if(-not(Test-Path $p)){throw "Missing required Data Bridge path: $p"}
}

$cfg = Get-Content $config -Raw | ConvertFrom-Json
$target = [int]$cfg.target_shard_mb
if($target -le 0){$target=400}

& python $packer --canonical-root $canonical --out-root $outRoot --config $config --target-shard-mb $target
if($LASTEXITCODE -ne 0){throw "Data Bridge pack failed"}

$latest = Get-Content (Join-Path $outRoot "LATEST.json") -Raw | ConvertFrom-Json
$datasetId = [string]$latest.dataset_id
$datasetDir = [string]$latest.dataset_dir
$tag = [string]$latest.release_tag
if(-not(Test-Path $datasetDir)){throw "Dataset directory missing: $datasetDir"}

$assets = @(Get-ChildItem $datasetDir -File | Where-Object {
  $_.Name -in @("DATASET_MANIFEST.json","DATASET_MANIFEST.csv","DATASET_SYMBOLS.csv") -or $_.Name -like "shard_*.zip"
})
if($assets.Count -lt 4){throw "Data Bridge package is incomplete"}

Write-Host ""
Write-Host ("Dataset ID : " + $datasetId)
Write-Host ("Release tag: " + $tag)
Write-Host ("Assets     : " + $assets.Count)

# Windows PowerShell 5.1 promotes native stderr to ErrorRecord. A missing
# release is an expected probe result, not a publisher failure, so temporarily
# relax ErrorActionPreference only for this lookup and branch on the exit code.
$probeEap = $ErrorActionPreference
try {
  $ErrorActionPreference = "Continue"
  $releaseJson = & $gh release view $tag --repo $repo --json assets 2>$null
  $releaseViewExit = $LASTEXITCODE
}
finally {
  $ErrorActionPreference = $probeEap
}
$releaseExists = ($releaseViewExit -eq 0)
if(-not $releaseExists){
  & $gh release create $tag --repo $repo --title ("Drummond dataset " + $datasetId) --notes ("Immutable DRUMMOND Data Bridge 01 dataset. Content identity: " + $datasetId) --prerelease
  if($LASTEXITCODE -ne 0){throw "Failed to create dataset release $tag"}
  $existing = @()
} else {
  $obj = $releaseJson | ConvertFrom-Json
  $existing = @($obj.assets | ForEach-Object { $_.name })
  Write-Host "Release already exists; existing assets will not be overwritten."
}

foreach($asset in $assets){
  if($existing -contains $asset.Name){
    Write-Host ("[KEEP] " + $asset.Name)
    continue
  }
  Write-Host ("[UPLOAD] " + $asset.Name + " (" + $asset.Length + " bytes)")
  & $gh release upload $tag $asset.FullName --repo $repo
  if($LASTEXITCODE -ne 0){throw "Failed to upload $($asset.Name)"}
}

Write-Host ""
Write-Host "Triggering GitHub Data Bridge verification/factory workflow..."
& $gh workflow run "data-bridge01.yml" --repo $repo -f ("dataset_tag=" + $tag) -f ("dataset_id=" + $datasetId)
if($LASTEXITCODE -ne 0){throw "Failed to trigger data-bridge01.yml"}

Start-Sleep -Seconds 2
& $gh run list --repo $repo --workflow "data-bridge01.yml" --limit 3

Write-Host ""
Write-Host "CLOUD DATA BRIDGE 01 PUBLISH PASS"
Write-Host ("DATASET_ID=" + $datasetId)
Write-Host ("TAG=" + $tag)
Write-Host "The dataset assets are outside normal Git history."
