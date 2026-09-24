param(
  [string]$DataFolder = ""
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

# Two supported layouts:
# A) repository: scripts\16_INSTALL_VPS.ps1 + DRUMMOND_TRADER_DEMO_02_FIX2\...
# B) standalone package: 16_INSTALL_VPS.ps1 + MQL4\Include\AuthorEngine + MQL4\Experts\...
$packageEngine = Join-Path $PSScriptRoot "MQL4\Include\AuthorEngine"
$packageWatcher = Join-Path $PSScriptRoot "MQL4\Experts\DrummondAuthorShadow_16.mq4"

if ((Test-Path $packageEngine) -and (Test-Path $packageWatcher)) {
  $engine = $packageEngine
  $watcher = $packageWatcher
  $sourceLayout = "STANDALONE_PACKAGE"
}
else {
  $src = Join-Path $repo "DRUMMOND_TRADER_DEMO_02_FIX2"
  $engine = Join-Path $src "AuthorEngine"
  $watcher = Join-Path $src "DrummondAuthorShadow_16.mq4"
  $sourceLayout = "REPOSITORY"
}

if (!(Test-Path $engine)) { throw "AuthorEngine source not found: $engine" }
if (!(Test-Path $watcher)) { throw "Watcher source not found: $watcher" }

function Test-TerminalFolder([string]$p) {
  return (Test-Path (Join-Path $p "MQL4\Experts")) -and
         (Test-Path (Join-Path $p "MQL4\Include"))
}

if ([string]::IsNullOrWhiteSpace($DataFolder)) {
  $base = Join-Path $env:APPDATA "MetaQuotes\Terminal"
  $candidates = @()
  if (Test-Path $base) {
    $candidates = Get-ChildItem $base -Directory | Where-Object { Test-TerminalFolder $_.FullName }
  }

  # Prefer the terminal where C01 Forward 14 is already installed.
  $preferred = @($candidates | Where-Object {
    (Test-Path (Join-Path $_.FullName "MQL4\Experts\DrummondWatcher_C01_FORWARD_14.mq4")) -or
    (Test-Path (Join-Path $_.FullName "MQL4\Experts\DrummondWatcher_C01_FORWARD_14.ex4"))
  })

  if ($preferred.Count -eq 1) {
    $DataFolder = $preferred[0].FullName
  }
  elseif ($candidates.Count -eq 1) {
    $DataFolder = $candidates[0].FullName
  }
  else {
    Write-Host ""
    Write-Host "MT4 data folders found:"
    foreach ($c in $candidates) { Write-Host "  $($c.FullName)" }
    Write-Host ""
    throw "Cannot choose MT4 terminal uniquely. Re-run with -DataFolder '<path from MT4 File -> Open Data Folder>'."
  }
}

$DataFolder = (Resolve-Path $DataFolder).Path
if (!(Test-TerminalFolder $DataFolder)) {
  throw "Not an MT4 Data Folder: $DataFolder"
}

$includeTarget = Join-Path $DataFolder "MQL4\Include\AuthorEngine"
$expertTarget = Join-Path $DataFolder "MQL4\Experts"

New-Item -ItemType Directory -Force -Path $includeTarget | Out-Null
Copy-Item (Join-Path $engine "*.mqh") $includeTarget -Force
Copy-Item $watcher $expertTarget -Force

$expected = @(
  "AE_Utils.mqh","AE_Dots.mqh","AE_Lines.mqh","AE_State.mqh",
  "AE_Envelope.mqh","AE_Energy.mqh","AE_Congestion.mqh",
  "AE_Filters.mqh","AE_Signals.mqh","AE_TradeManager.mqh","AE_All.mqh"
)
foreach ($f in $expected) {
  $p = Join-Path $includeTarget $f
  if (!(Test-Path $p)) { throw "Install verification failed: $p" }
}
$installedWatcher = Join-Path $expertTarget "DrummondAuthorShadow_16.mq4"
if (!(Test-Path $installedWatcher)) { throw "Install verification failed: $installedWatcher" }

Write-Host ""
Write-Host "============================================================"
Write-Host "DRUMMOND AUTHOR ENGINE 16 VPS INSTALL PASS"
Write-Host "============================================================"
Write-Host "Source layout   : $sourceLayout"
Write-Host "MT4 Data Folder : $DataFolder"
Write-Host "Include         : $includeTarget"
Write-Host "Expert          : $installedWatcher"
Write-Host "Modules         : $($expected.Count)"
Write-Host "Trading         : DISABLED BY DESIGN"
Write-Host ""
Write-Host "NEXT:"
Write-Host "1. Open MetaEditor"
Write-Host "2. Open MQL4\Experts\DrummondAuthorShadow_16.mq4"
Write-Host "3. Press F7"
Write-Host "4. Required result: 0 errors, 0 warnings"
Write-Host "============================================================"
