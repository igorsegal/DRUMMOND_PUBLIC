$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$out  = Join-Path $root "docs\INVENTORY.md"
$git = Get-Command git -ErrorAction SilentlyContinue
if ($git) {
    $gitExe = $git.Source
}
elseif (Test-Path "D:\Git\cmd\git.exe") {
    $gitExe = "D:\Git\cmd\git.exe"
}
else {
    throw "git executable not found"
}
$tracked = & $gitExe -C $root ls-files
if ($LASTEXITCODE -ne 0) {
    throw "git ls-files failed"
}
$tracked = @($tracked | Where-Object { $_ -ne "docs/INVENTORY.md" })
# git ls-files is already path-sorted. Preserve that order verbatim so
# inventory generation is identical across PowerShell/.NET cultures.
$rows = foreach ($relative in $tracked) {
    $category =
        if ($relative -like ".github/*") { "GitHub Actions" }
        elseif ($relative -like "DRUMMOND_TRADER_*") { "Production source" }
        elseif ($relative -like "BASELINE/*") { "Baseline" }
        elseif ($relative -like "tests/*") { "Tests" }
        elseif ($relative -like "scripts/*") { "Scripts" }
        elseif ($relative -like "docs/*") { "Documentation" }
        elseif ($relative -like "config/*") { "Configuration" }
        elseif ($relative -like "data/*") { "Test data / manifest" }
        elseif ($relative -like "results/*") { "Results" }
        elseif ($relative -like "src/*") { "Future source layout" }
        elseif ($relative -like "include/*") { "Future include layout" }
        else { "Repository root" }
    [PSCustomObject]@{
        Category = $category
        Path     = $relative
    }
}
$totalFiles = @($rows).Count
$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("# DRUMMOND CLOUD — REPOSITORY INVENTORY")
$lines.Add("")
$lines.Add("AUTO-GENERATED FILE. DO NOT EDIT MANUALLY.")
$lines.Add("")
$lines.Add("Tracked files: $totalFiles")
$lines.Add("")
$groups = $rows | Group-Object Category | Sort-Object Name
foreach ($group in $groups) {
    $lines.Add("## $($group.Name)")
    $lines.Add("")
    foreach ($row in $group.Group) {
        $lines.Add("- $($row.Path)")
    }
    $lines.Add("")
}
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($out, $lines, $utf8NoBom)
Write-Host ""
Write-Host "DRUMMOND REPOSITORY INVENTORY PASS"
Write-Host "Files : $totalFiles"
Write-Host "Output: $out"
