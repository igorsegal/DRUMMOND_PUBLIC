$ErrorActionPreference = "Stop"
$root      = Split-Path $PSScriptRoot -Parent
$builder   = Join-Path $root "scripts\build-inventory.ps1"
$inventory = Join-Path $root "docs\INVENTORY.md"
if (-not (Test-Path $builder)) {
    throw "FAIL: missing inventory builder"
}
if (-not (Test-Path $inventory)) {
    throw "FAIL: missing docs/INVENTORY.md"
}
& $builder
if ($LASTEXITCODE -ne 0) {
    throw "FAIL: inventory builder failed"
}
$git = Get-Command git -ErrorAction SilentlyContinue
if ($git) {
    $gitExe = $git.Source
}
elseif (Test-Path "D:\Git\cmd\git.exe") {
    $gitExe = "D:\Git\cmd\git.exe"
}
else {
    throw "FAIL: git executable not found"
}
& $gitExe -C $root diff --exit-code -- docs/INVENTORY.md
if ($LASTEXITCODE -ne 0) {
    throw "FAIL: docs/INVENTORY.md is stale"
}
Write-Host ""
Write-Host "DRUMMOND INVENTORY CONTRACT PASS"
