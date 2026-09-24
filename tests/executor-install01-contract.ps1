$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$installer = Join-Path $root "scripts\install-mt4-executor-eq01.ps1"
$prepare = Join-Path $root "scripts\prepare-mt4-executor-eq01.ps1"
$prod = Join-Path $root "DRUMMOND_TRADER_DEMO_02_FIX2\DrummondExecutor_DEMO_02.mq4"
$eq = Join-Path $root "DRUMMOND_TRADER_DEMO_02_FIX2\DrummondExecutor_EQ01.mq4"

foreach ($p in @($installer,$prepare,$prod,$eq)) {
    if (-not (Test-Path $p)) { throw "FAIL: missing $p" }
    if ((Get-Item $p).Length -eq 0) { throw "FAIL: empty $p" }
}

$prodText = (Get-Content $prod -Raw).Replace("`r`n","`n")
$eqText = (Get-Content $eq -Raw).Replace("`r`n","`n")
$expected = $prodText.Replace(
    "input D2_EXECUTOR_RUN_MODE InpRunMode=D2_EXECUTOR_DEMO;",
    "input D2_EXECUTOR_RUN_MODE InpRunMode=D2_EXECUTOR_TESTER;"
)
if ($expected -eq $prodText) { throw "FAIL: production run-mode declaration not found" }
if ($eqText -ne $expected) { throw "FAIL: DrummondExecutor_EQ01 differs from production by more than the frozen TESTER default" }

$installerText = Get-Content $installer -Raw
$prepareText = Get-Content $prepare -Raw

foreach ($token in @("HST_SOURCE_SELECTION.json","DrummondExecutor_EQ01.mq4","DT02_Common.mqh","MQL4\Experts","metaeditor64.exe","DRUMMOND EXECUTOR EQ01 INSTALL PASS")) {
    if ($installerText -notlike "*$token*") { throw "FAIL: installer missing token $token" }
}
foreach ($token in @("install-mt4-executor-eq01.ps1","tester\files","DRUMMOND_DEMO02_SIGNALS.csv","DrummondExecutor_EQ01","hard-fixed TESTER")) {
    if ($prepareText -notlike "*$token*") { throw "FAIL: prepare missing token $token" }
}

Write-Host "MT4 EXECUTOR EQ01 FIXED-MODE CONTRACT PASS"
