@echo off
setlocal
cd /d "%~dp0.."

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0collect-mt4-hst-equivalence01.ps1"
set RC=%ERRORLEVEL%

"D:\Git\cmd\git.exe" -C "%CD%" add "data/mt4_equivalence01/hst" "results/latest/equivalence01_hst"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-inventory.ps1"
"D:\Git\cmd\git.exe" -C "%CD%" add "docs/INVENTORY.md"
"D:\Git\cmd\git.exe" -C "%CD%" commit -m "Add MT4 HST equivalence evidence"
if errorlevel 1 goto :commit_failed
"D:\Git\cmd\git.exe" -C "%CD%" push
if errorlevel 1 goto :push_failed

echo.
if %RC%==0 (
  echo MT4 HST EQUIVALENCE 01 PASS
) else (
  echo MT4 HST EQUIVALENCE 01 mismatch report was pushed to GitHub.
)
pause
exit /b %RC%

:commit_failed
echo.
echo Git commit failed.
pause
exit /b 1

:push_failed
echo.
echo Git push failed.
pause
exit /b 1
