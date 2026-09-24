$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$src  = Join-Path $root "DRUMMOND_TRADER_DEMO_02_FIX2"
$executor = Join-Path $src "DrummondExecutor_DEMO_02.mq4"
$watcher  = Join-Path $src "DrummondWatcher_DEMO_02.mq4"
$common   = Join-Path $src "DT02_Common.mqh"
function Assert-Contains {
    param(
        [string]$File,
        [string]$Pattern,
        [string]$Name
    )
    if (-not (Select-String -Path $File -Pattern $Pattern -Quiet)) {
        throw "FAIL: $Name"
    }
    Write-Host "[OK] $Name"
}
foreach ($file in @($executor,$watcher,$common)) {
    if (-not (Test-Path $file)) {
        throw "FAIL: missing file $file"
    }
    if ((Get-Item $file).Length -eq 0) {
        throw "FAIL: empty file $file"
    }
    Write-Host "[OK] exists: $(Split-Path $file -Leaf)"
}
Assert-Contains $executor '#include\s+"DT02_Common\.mqh"' `
    "Executor uses DT02_Common.mqh"
Assert-Contains $watcher '#include\s+"DT02_Common\.mqh"' `
    "Watcher uses DT02_Common.mqh"
Assert-Contains $executor 'DRUMMOND_DEMO02_SIGNALS\.csv' `
    "Executor uses SIGNALS queue"
Assert-Contains $executor 'DRUMMOND_DEMO02_EXECUTION\.csv' `
    "Executor uses EXECUTION audit"
Assert-Contains $watcher 'DRUMMOND_DEMO02_SIGNALS\.csv' `
    "Watcher produces SIGNALS queue"
Assert-Contains $watcher 'DRUMMOND_DEMO02_WATCHER\.csv' `
    "Watcher uses WATCHER audit"
Assert-Contains $executor 'FILE_COMMON' `
    "Executor uses MetaTrader Common Files"
Assert-Contains $watcher 'FILE_COMMON' `
    "Watcher uses MetaTrader Common Files"
foreach ($file in @($executor,$watcher,$common)) {
    if (Select-String -Path $file -Pattern '[A-Za-z]:\\' -Quiet) {
        throw "FAIL: absolute Windows path found in $(Split-Path $file -Leaf)"
    }
}
Write-Host ""
Write-Host "DRUMMOND SOURCE CONTRACT PASS"
