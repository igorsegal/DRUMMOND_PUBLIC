$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$root = Split-Path $PSScriptRoot -Parent
$selection = Join-Path $root "results\latest\equivalence01_hst\HST_SOURCE_SELECTION.json"
$analyzer = Join-Path $root "scripts\executor_lifecycle02.py"
$localData = Join-Path $root "data\mt4_lifecycle02"
$localHst = Join-Path $localData "hst\XAUUSD5.hst"
$out = Join-Path $root "results\latest\executor_lifecycle02"

foreach($p in @($selection,$analyzer,$localHst)){if(-not(Test-Path $p)){throw "Missing required file: $p"}}
$sel=Get-Content $selection -Raw | ConvertFrom-Json
$historyServer=[string]$sel.parent
$historyRoot=Split-Path $historyServer -Parent
$terminalData=Split-Path $historyRoot -Parent
$testerFiles=Join-Path $terminalData "tester\files"
$queue=Join-Path $testerFiles "DRUMMOND_DEMO02_SIGNALS.csv"
$execution=Join-Path $testerFiles "DRUMMOND_DEMO02_EXECUTION.csv"
$lifecycle=Join-Path $testerFiles "DRUMMOND_DEMO02_LIFECYCLE.csv"

foreach($p in @($queue,$execution,$lifecycle)){if(-not(Test-Path $p)){throw "Missing Lifecycle 02 tester evidence: $p"}}
New-Item -ItemType Directory -Force -Path $localData | Out-Null
Copy-Item $queue (Join-Path $localData "DRUMMOND_DEMO02_SIGNALS.csv") -Force
Copy-Item $execution (Join-Path $localData "DRUMMOND_DEMO02_EXECUTION.csv") -Force
Copy-Item $lifecycle (Join-Path $localData "DRUMMOND_DEMO02_LIFECYCLE.csv") -Force
if(Test-Path $out){Remove-Item $out -Recurse -Force}

& python $analyzer analyze --queue (Join-Path $localData "DRUMMOND_DEMO02_SIGNALS.csv") --execution (Join-Path $localData "DRUMMOND_DEMO02_EXECUTION.csv") --lifecycle (Join-Path $localData "DRUMMOND_DEMO02_LIFECYCLE.csv") --m5 $localHst --out $out --spread-points 20
$code=$LASTEXITCODE

Write-Host ""
Write-Host ("Lifecycle evidence: " + $lifecycle)
if($code -eq 0){Write-Host "EXECUTOR LIFECYCLE 02 PASS"}else{Write-Host "EXECUTOR LIFECYCLE 02 produced a deterministic mismatch report."}
exit $code
