$ErrorActionPreference = "Stop"

$root = Split-Path $PSScriptRoot -Parent
$eq01 = Join-Path $root "DRUMMOND_TRADER_DEMO_02_FIX2\DrummondExecutor_EQ01.mq4"
$eq02 = Join-Path $root "DRUMMOND_TRADER_DEMO_02_FIX2\DrummondExecutor_EQ02.mq4"

foreach($p in @($eq01,$eq02)){if(-not(Test-Path $p)){throw "FAIL: missing $p"}}
$a=Get-Content $eq01 -Raw
$b=Get-Content $eq02 -Raw

function Get-FunctionBlock([string]$text,[string]$signature) {
    $start=$text.IndexOf($signature)
    if($start -lt 0){throw "FAIL: missing function $signature"}
    $brace=$text.IndexOf("{",$start)
    if($brace -lt 0){throw "FAIL: missing function body $signature"}
    $depth=0
    for($i=$brace;$i -lt $text.Length;$i++){
        if($text[$i] -eq "{"){$depth++}
        elseif($text[$i] -eq "}"){$depth--;if($depth -eq 0){return $text.Substring($start,$i-$start+1)}}
    }
    throw "FAIL: unclosed function $signature"
}

foreach($sig in @(
  "bool D2_EnvironmentOK",
  "bool D2_ValidateFreshSignal",
  "void D2_ReadQueueAndExecute",
  "void D2_TrailAllOurPositions"
)){
    $x=Get-FunctionBlock $a $sig
    $y=Get-FunctionBlock $b $sig
    if($x -ne $y){throw "FAIL: trading function changed in EQ02: $sig"}
}

foreach($token in @(
  'input D2_EXECUTOR_RUN_MODE InpRunMode=D2_EXECUTOR_TESTER;',
  'OrderSend(sym,command,lots,currentPrice,InpSlippagePoints',
  'D2_TrailAllOurPositions();',
  'D2_ReadQueueAndExecute();',
  'InpLifecycleFile="DRUMMOND_DEMO02_LIFECYCLE.csv"',
  'D2_ScanClosedLifecycle();',
  'D2_LifecycleLogOpen(signalId,ticket);'
)){
    if($b -notlike "*$token*"){throw "FAIL: EQ02 missing required token $token"}
}

if($b -notmatch 'D2_ScanClosedLifecycle\(\);\s*D2_TrailAllOurPositions\(\);\s*D2_ReadQueueAndExecute\(\);'){
    throw "FAIL: EQ02 OnTick order changed"
}

Write-Host "EXECUTOR EQ02 SOURCE CONTRACT PASS"
