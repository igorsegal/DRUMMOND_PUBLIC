param(
    [switch]$Push
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$root = Split-Path $PSScriptRoot -Parent
$terminalRoot = Join-Path $env:APPDATA "MetaQuotes\Terminal"
$input = Join-Path $root "data\mt4_equivalence01"
$out = Join-Path $root "results\latest\equivalence01"

if (-not (Test-Path $terminalRoot)) { throw "MetaQuotes terminal root not found: $terminalRoot" }

$candidates = @()
Get-ChildItem $terminalRoot -Directory | ForEach-Object {
    $files = Join-Path $_.FullName "tester\files"
    $w = Join-Path $files "DRUMMOND_DEMO02_WATCHER.csv"
    $s = Join-Path $files "DRUMMOND_DEMO02_SIGNALS.csv"
    if ((Test-Path $w) -and (Test-Path $s)) {
        $candidates += [PSCustomObject]@{
            Folder=$_.FullName
            Watcher=$w
            Signals=$s
            Time=(Get-Item $w).LastWriteTimeUtc
        }
    }
}
if ($candidates.Count -eq 0) { throw "No MT4 tester output pair found under $terminalRoot" }
$pick = $candidates | Sort-Object Time -Descending | Select-Object -First 1

$sample = Import-Csv $pick.Watcher -Delimiter ';' | Where-Object { $_.SYMBOL -eq "XAUUSD" }
if (@($sample).Count -lt 1000) {
    throw "Newest watcher output is not a full XAUUSD equivalence run (XAUUSD rows < 1000): $($pick.Watcher)"
}

New-Item -ItemType Directory -Force -Path $input | Out-Null
Copy-Item $pick.Watcher (Join-Path $input "DRUMMOND_DEMO02_WATCHER.csv") -Force
Copy-Item $pick.Signals (Join-Path $input "DRUMMOND_DEMO02_SIGNALS.csv") -Force

Write-Host "Collected MT4 tester evidence from:"
Write-Host $pick.Folder
Write-Host ""

& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tests\equivalence01-real.ps1")
$compareCode=$LASTEXITCODE

if ($Push) {
    $git = if (Test-Path "D:\Git\cmd\git.exe") { "D:\Git\cmd\git.exe" } else { (Get-Command git).Source }
    & $git -C $root add "data/mt4_equivalence01/DRUMMOND_DEMO02_WATCHER.csv" "data/mt4_equivalence01/DRUMMOND_DEMO02_SIGNALS.csv"
    if (Test-Path $out) { & $git -C $root add "results/latest/equivalence01" }
    & (Join-Path $root "scripts\build-inventory.ps1")
    & $git -C $root add "docs/INVENTORY.md"
    & $git -C $root commit -m "Add MT4 Equivalence 01 runtime evidence"
    if ($LASTEXITCODE -ne 0) { throw "git commit failed" }
    & $git -C $root push
    if ($LASTEXITCODE -ne 0) { throw "git push failed" }
    Write-Host "MT4 equivalence evidence pushed to GitHub."
}
exit $compareCode
