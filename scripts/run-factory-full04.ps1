$ErrorActionPreference = "Stop"

$root = Split-Path $PSScriptRoot -Parent
$gh = "D:\GitHub CLI\gh.exe"
$repo = "igorsegal/DRUMMOND_CLOUD"
$workflow = "factory-full04.yml"

$datasetId = "DRUMMOND_CANONICAL_8E9A1D784E3893D9"
$datasetTag = "dataset03-drummond_canonical_8e9a1d784e3893d9"

if (-not (Test-Path $gh)) { throw "GitHub CLI not found: $gh" }

Write-Host "========================================"
Write-Host "DRUMMOND CLOUD FACTORY 02 FULL 04"
Write-Host "========================================"
Write-Host ("DATASET_ID=" + $datasetId)
Write-Host ("TAG=" + $datasetTag)
Write-Host ""
Write-Host "Triggering full lifecycle workflow..."

& $gh workflow run $workflow --repo $repo -f ("dataset_tag=" + $datasetTag) -f ("dataset_id=" + $datasetId)
if ($LASTEXITCODE -ne 0) { throw "Failed to trigger $workflow" }

Start-Sleep -Seconds 2
& $gh run list --repo $repo --workflow $workflow --limit 3
if ($LASTEXITCODE -ne 0) { throw "Failed to list Factory 04 runs" }

Write-Host ""
Write-Host "CLOUD FACTORY 02 FULL 04 TRIGGER PASS"
