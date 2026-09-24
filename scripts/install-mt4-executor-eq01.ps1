$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$root = Split-Path $PSScriptRoot -Parent
$selection = Join-Path $root "results\latest\equivalence01_hst\HST_SOURCE_SELECTION.json"
$srcDir = Join-Path $root "DRUMMOND_TRADER_DEMO_02_FIX2"
$srcExecutor = Join-Path $srcDir "DrummondExecutor_EQ01.mq4"
$srcCommon = Join-Path $srcDir "DT02_Common.mqh"

foreach ($p in @($selection,$srcExecutor,$srcCommon)) {
    if (-not (Test-Path $p)) { throw "Missing required file: $p" }
}

$sel = Get-Content $selection -Raw | ConvertFrom-Json
$historyServer = [string]$sel.parent
$historyRoot = Split-Path $historyServer -Parent
$terminalData = Split-Path $historyRoot -Parent
$expertsRoot = Join-Path $terminalData "MQL4\Experts"

if (-not (Test-Path $expertsRoot)) {
    New-Item -ItemType Directory -Force -Path $expertsRoot | Out-Null
}

$watchers = @(Get-ChildItem $expertsRoot -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -in @("DrummondWatcher_DEMO_02.mq4","DrummondWatcher_DEMO_02.ex4") })

if ($watchers.Count -gt 0) {
    $targetDir = $watchers[0].DirectoryName
}
else {
    $targetDir = Join-Path $expertsRoot "DRUMMOND_CLOUD"
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
}

$dstExecutor = Join-Path $targetDir "DrummondExecutor_EQ01.mq4"
$dstCommon = Join-Path $targetDir "DT02_Common.mqh"
$dstEx4 = Join-Path $targetDir "DrummondExecutor_EQ01.ex4"

Copy-Item $srcExecutor $dstExecutor -Force
Copy-Item $srcCommon $dstCommon -Force

Write-Host ("Installed source: " + $dstExecutor)
Write-Host ("Installed include: " + $dstCommon)

$compiled = Test-Path $dstEx4
$originFile = Join-Path $terminalData "origin.txt"
$meta = $null

if (Test-Path $originFile) {
    $origin = (Get-Content $originFile -Raw).Trim()
    if ($origin) {
        $base = if (Test-Path $origin -PathType Container) { $origin } else { Split-Path $origin -Parent }
        foreach ($name in @("metaeditor64.exe","metaeditor.exe")) {
            $candidate = Join-Path $base $name
            if (Test-Path $candidate) { $meta = $candidate; break }
        }
    }
}

if ($meta) {
    $log = Join-Path $targetDir "DrummondExecutor_EQ01.compile.log"
    if (Test-Path $log) { Remove-Item $log -Force }
    $before = if (Test-Path $dstEx4) { (Get-Item $dstEx4).LastWriteTimeUtc } else { [datetime]::MinValue }
    $compileArg = '/compile:"' + $dstExecutor + '"'
    $logArg = '/log:"' + $log + '"'
    Start-Process -FilePath $meta -ArgumentList @($compileArg,$logArg) -Wait | Out-Null
    Start-Sleep -Milliseconds 500
    if (Test-Path $dstEx4) {
        $after = (Get-Item $dstEx4).LastWriteTimeUtc
        if ($after -ge $before) { $compiled = $true }
    }
    if (Test-Path $log) {
        Write-Host ""
        Write-Host "MetaEditor compile log:"
        Get-Content $log | Select-Object -Last 20
    }
}

Write-Host ""
Write-Host ("MT4 data folder : " + $terminalData)
Write-Host ("Expert folder   : " + $targetDir)
Write-Host ("Executor EX4    : " + $(if ($compiled) { "READY" } else { "NOT BUILT" }))

if (-not $compiled) {
    Write-Host ""
    Write-Host "AUTO-COMPILE DID NOT PRODUCE EX4."
    Write-Host "Open this exact file in MetaEditor and press Compile:"
    Write-Host $dstExecutor
    exit 2
}

Write-Host ""
Write-Host "DRUMMOND EXECUTOR EQ01 INSTALL PASS"
exit 0
