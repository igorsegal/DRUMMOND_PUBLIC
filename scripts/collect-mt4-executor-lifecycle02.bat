@echo off
setlocal
cd /d "%~dp0.."

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0collect-mt4-executor-lifecycle02.ps1"
set RC=%ERRORLEVEL%

if not exist "data\mt4_lifecycle02\DRUMMOND_DEMO02_LIFECYCLE.csv" (
  echo.
  echo Lifecycle evidence was not created. Nothing will be committed.
  pause
  exit /b %RC%
)

"D:\Git\cmd\git.exe" -C "%CD%" add "data/mt4_lifecycle02" "results/latest/executor_lifecycle02"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-inventory.ps1"
if errorlevel 1 goto :inventory_failed
"D:\Git\cmd\git.exe" -C "%CD%" add "docs/INVENTORY.md"
"D:\Git\cmd\git.exe" -C "%CD%" commit -m "Add MT4 Executor Lifecycle 02 evidence"
if errorlevel 1 goto :commit_failed
"D:\Git\cmd\git.exe" -C "%CD%" push
if errorlevel 1 goto :push_failed

echo.
if %RC%==0 (
  echo EXECUTOR LIFECYCLE 02 PASS
) else (
  echo EXECUTOR LIFECYCLE 02 mismatch report pushed to GitHub.
)
pause
exit /b %RC%

:inventory_failed
echo Inventory build failed.
pause
exit /b 1
:commit_failed
echo Git commit failed.
pause
exit /b 1
:push_failed
echo Git push failed.
pause
exit /b 1
