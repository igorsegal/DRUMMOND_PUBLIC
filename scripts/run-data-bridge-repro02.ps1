$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$root = Split-Path $PSScriptRoot -Parent
$gh = "D:\GitHub CLI\gh.exe"
$repo = "igorsegal/DRUMMOND_CLOUD"
$workflow = "data-bridge-repro02.yml"

$datasetId = "DRUMMOND_CANONICAL_649F9CB77BB7E0FE"
$datasetTag = "dataset-drummond_canonical_649f9cb77bb7e0fe"

if (-not (Test-Path $gh)) { throw "GitHub CLI not found: $gh" }

Write-Host "========================================"
Write-Host "DRUMMOND CLOUD DATA BRIDGE REPRO 02"
Write-Host "========================================"
Write-Host ("DATASET_ID=" + $datasetId)
Write-Host ("TAG=" + $datasetTag)
Write-Host ""
Write-Host "Triggering reproducibility workflow..."

& $gh workflow run $workflow --repo $repo -f ("dataset_tag=" + $datasetTag) -f ("dataset_id=" + $datasetId)
if ($LASTEXITCODE -ne 0) { throw "Failed to trigger $workflow" }

Start-Sleep -Seconds 2
& $gh run list --repo $repo --workflow $workflow --limit 3
if ($LASTEXITCODE -ne 0) { throw "Failed to list Repro 02 runs" }

Write-Host ""
Write-Host "CLOUD DATA BRIDGE REPRO 02 TRIGGER PASS"
