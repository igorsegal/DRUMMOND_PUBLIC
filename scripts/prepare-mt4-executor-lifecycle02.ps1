$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$root = Split-Path $PSScriptRoot -Parent
$selection = Join-Path $root "results\latest\equivalence01_hst\HST_SOURCE_SELECTION.json"
$srcDir = Join-Path $root "DRUMMOND_TRADER_DEMO_02_FIX2"
$src = Join-Path $srcDir "DrummondExecutor_EQ02.mq4"
$common = Join-Path $srcDir "DT02_Common.mqh"
$queue = Join-Path $root "data\mt4_executor_eq01\DRUMMOND_DEMO02_SIGNALS.csv"
$localData = Join-Path $root "data\mt4_lifecycle02"
$localHst = Join-Path $localData "hst"

foreach ($p in @($selection,$src,$common,$queue)) { if (-not (Test-Path $p)) { throw "Missing required file: $p" } }
$sel = Get-Content $selection -Raw | ConvertFrom-Json
$historyServer = [string]$sel.parent
$historyRoot = Split-Path $historyServer -Parent
$terminalData = Split-Path $historyRoot -Parent
$expertsRoot = Join-Path $terminalData "MQL4\Experts"
$testerFiles = Join-Path $terminalData "tester\files"

$eq01 = @(Get-ChildItem $expertsRoot -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -in @("DrummondExecutor_EQ01.mq4","DrummondExecutor_EQ01.ex4") } | Select-Object -First 1)
$targetDir = if ($eq01.Count -gt 0) { $eq01[0].DirectoryName } else { Join-Path $expertsRoot "DRUMMOND_CLOUD" }
New-Item -ItemType Directory -Force -Path $targetDir,$testerFiles,$localHst | Out-Null

$dst = Join-Path $targetDir "DrummondExecutor_EQ02.mq4"
$dstCommon = Join-Path $targetDir "DT02_Common.mqh"
$dstEx4 = Join-Path $targetDir "DrummondExecutor_EQ02.ex4"
Copy-Item $src $dst -Force
Copy-Item $common $dstCommon -Force

$originFile = Join-Path $terminalData "origin.txt"
$meta = $null
if (Test-Path $originFile) {
  $origin=(Get-Content $originFile -Raw).Trim()
  if ($origin) {
    $base = if (Test-Path $origin -PathType Container) { $origin } else { Split-Path $origin -Parent }
    foreach($name in @("metaeditor64.exe","metaeditor.exe")) { $candidate=Join-Path $base $name; if(Test-Path $candidate){$meta=$candidate;break} }
  }
}
if (-not $meta) { throw "MetaEditor not found from terminal origin.txt" }
$log=Join-Path $targetDir "DrummondExecutor_EQ02.compile.log"
if(Test-Path $log){Remove-Item $log -Force}
$compileArg='/compile:"' + $dst + '"'
$logArg='/log:"' + $log + '"'
Start-Process -FilePath $meta -ArgumentList @($compileArg,$logArg) -Wait | Out-Null
Start-Sleep -Milliseconds 500
if(Test-Path $log){Get-Content $log | Select-Object -Last 20}
if(-not (Test-Path $dstEx4)){throw "EQ02 compile did not produce EX4: $dstEx4"}

$m5 = Join-Path $historyServer "XAUUSD5.hst"
if(-not (Test-Path $m5)){throw "Exact MT4 M5 history not found: $m5"}
Copy-Item $m5 (Join-Path $localHst "XAUUSD5.hst") -Force
Copy-Item $queue (Join-Path $testerFiles "DRUMMOND_DEMO02_SIGNALS.csv") -Force
foreach($name in @("DRUMMOND_DEMO02_EXECUTION.csv","DRUMMOND_DEMO02_LIFECYCLE.csv")){
  $p=Join-Path $testerFiles $name; if(Test-Path $p){Remove-Item $p -Force}
}

Write-Host ""
Write-Host "EXECUTOR LIFECYCLE 02 PREPARED"
Write-Host ("Expert       : DrummondExecutor_EQ02")
Write-Host ("MT4 data     : " + $terminalData)
Write-Host ("M5 HST       : " + $m5)
Write-Host ("M5 copied to : " + (Join-Path $localHst "XAUUSD5.hst"))
Write-Host "Symbol       : XAUUSD"
Write-Host "Period       : M5"
Write-Host "Model        : Open prices only"
Write-Host "Use Date     : 2026-01-01 -> 2026-08-27"
Write-Host "Spread       : 20"
Write-Host "Run mode     : hard-fixed TESTER"
Write-Host "Lifecycle log: tester\files\DRUMMOND_DEMO02_LIFECYCLE.csv"
Write-Host "EXECUTOR LIFECYCLE 02 PREP PASS"
