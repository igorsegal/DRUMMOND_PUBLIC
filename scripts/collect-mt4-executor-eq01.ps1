$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$root = Split-Path $PSScriptRoot -Parent
$analyzer = Join-Path $root "scripts\mt4_executor_capture01.py"
$work = Join-Path $root "data\mt4_executor_eq01"
$out = Join-Path $root "results\latest\executor_capture01"
$terminalRoot = Join-Path $env:APPDATA "MetaQuotes\Terminal"

if (-not (Test-Path $terminalRoot)) { throw "MetaQuotes terminal root not found: $terminalRoot" }

$candidates = @()
Get-ChildItem $terminalRoot -Directory | ForEach-Object {
    $testerFiles = Join-Path $_.FullName "tester\files"
    $queue = Join-Path $testerFiles "DRUMMOND_DEMO02_SIGNALS.csv"
    $exec = Join-Path $testerFiles "DRUMMOND_DEMO02_EXECUTION.csv"
    if (Test-Path $exec) {
        $item = Get-Item $exec
        $candidates += [PSCustomObject]@{
            Terminal = $_.FullName
            TesterFiles = $testerFiles
            Queue = $queue
            Execution = $exec
            LastWriteTimeUtc = $item.LastWriteTimeUtc
            Length = $item.Length
        }
    }
}

if ($candidates.Count -eq 0) {
    Write-Host ""
    Write-Host "No DRUMMOND_DEMO02_EXECUTION.csv found in any MT4 tester\files folder."
    Write-Host "This means the Executor did not write an execution audit."
    Write-Host "Most common causes:"
    Write-Host "  1) InpRunMode was DEMO instead of TESTER"
    Write-Host "  2) InpEnableTesterTrading was false"
    Write-Host "  3) the Strategy Tester was run in a different MT4 installation before the queue was prepared"
    Write-Host ""
    throw "MT4 EXECUTOR CAPTURE 01: NO_EXECUTION_OUTPUT"
}

$pick = $candidates | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
if (-not (Test-Path $pick.Queue)) { throw "Selected execution has no matching queue: $($pick.Queue)" }
if ($pick.Length -le 0) { throw "Selected execution file is empty: $($pick.Execution)" }

Write-Host ("Selected MT4 terminal : " + $pick.Terminal)
Write-Host ("Selected execution    : " + $pick.Execution)
Write-Host ("Execution bytes       : " + $pick.Length)
Write-Host ("Execution timestamp   : " + $pick.LastWriteTimeUtc.ToString("o"))

New-Item -ItemType Directory -Force -Path $work | Out-Null
Copy-Item $pick.Queue (Join-Path $work "DRUMMOND_DEMO02_SIGNALS.csv") -Force
Copy-Item $pick.Execution (Join-Path $work "DRUMMOND_DEMO02_EXECUTION.csv") -Force

if (Test-Path $out) { Remove-Item $out -Recurse -Force }
& python $analyzer analyze --queue (Join-Path $work "DRUMMOND_DEMO02_SIGNALS.csv") --execution (Join-Path $work "DRUMMOND_DEMO02_EXECUTION.csv") --out $out --max-age-minutes 15
$code = $LASTEXITCODE

Write-Host ""
if ($code -eq 0) {
    Write-Host "MT4 EXECUTOR CAPTURE 01 PASS"
} else {
    Write-Host "MT4 EXECUTOR CAPTURE 01 produced a deterministic violation report."
}
exit $code
