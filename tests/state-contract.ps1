$ErrorActionPreference = "Stop"

$root  = Split-Path $PSScriptRoot -Parent
$state = Join-Path $root "docs\CURRENT_STATE.md"

if (-not (Test-Path $state)) {
    throw "FAIL: missing docs/CURRENT_STATE.md"
}

if ((Get-Item $state).Length -eq 0) {
    throw "FAIL: CURRENT_STATE.md is empty"
}

function Assert-StateContains {
    param(
        [string]$Pattern,
        [string]$Name
    )

    if (-not (Select-String -Path $state -Pattern $Pattern -Quiet)) {
        throw "FAIL: $Name"
    }

    Write-Host "[OK] $Name"
}

Assert-StateContains 'BASELINE PASS' `
    "Current state reports BASELINE PASS"

Assert-StateContains 'DRUMMOND_TRADER_DEMO_02_FIX2' `
    "Current production source is declared"

Assert-StateContains 'DrummondExecutor_DEMO_02\.mq4' `
    "Executor is declared"

Assert-StateContains 'DrummondWatcher_DEMO_02\.mq4' `
    "Watcher is declared"

Assert-StateContains 'DT02_Common\.mqh' `
    "Common include is declared"

Assert-StateContains 'DRUMMOND_DEMO02_EXECUTION\.csv' `
    "Execution baseline is declared"

Assert-StateContains 'DRUMMOND_DEMO02_SIGNALS\.csv' `
    "Signals baseline is declared"

Assert-StateContains 'DRUMMOND_DEMO02_WATCHER\.csv' `
    "Watcher baseline is declared"

Assert-StateContains 'baseline-check\.yml' `
    "GitHub workflow is declared"

Assert-StateContains 'source-contract\.ps1' `
    "Source contract is declared"

Assert-StateContains 'D:\\AHexaTrader\\1DataFiles\\raw' `
    "Canonical market data path is declared"

Assert-StateContains 'Never create or use TEMP/AppData RAW mirrors' `
    "Canonical RAW rule is declared"

Assert-StateContains 'Watcher -> SIGNALS queue -> Executor -> EXECUTION audit' `
    "Execution architecture is declared"

Assert-StateContains 'NEXT:' `
    "Next task is declared"

Write-Host ""
Write-Host "DRUMMOND CURRENT STATE CONTRACT PASS"
