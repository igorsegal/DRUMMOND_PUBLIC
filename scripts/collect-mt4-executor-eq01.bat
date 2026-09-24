@echo off
setlocal
cd /d "%~dp0.."

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0collect-mt4-executor-eq01.ps1"
set RC=%ERRORLEVEL%

if not "%RC%"=="0" (
  echo.
  echo MT4 EXECUTOR CAPTURE 01 collection failed before commit/push.
  echo Nothing was committed.
  pause
  exit /b %RC%
)

"D:\Git\cmd\git.exe" -C "%CD%" add "data/mt4_executor_eq01" "results/latest/executor_capture01"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-inventory.ps1"
if errorlevel 1 goto :inventory_failed

"D:\Git\cmd\git.exe" -C "%CD%" add "docs/INVENTORY.md"
"D:\Git\cmd\git.exe" -C "%CD%" commit -m "Add MT4 Executor capture evidence"
if errorlevel 1 goto :commit_failed
"D:\Git\cmd\git.exe" -C "%CD%" push
if errorlevel 1 goto :push_failed

echo.
echo MT4 EXECUTOR CAPTURE 01 PASS
pause
exit /b 0

:inventory_failed
echo.
echo Inventory build failed.
pause
exit /b 1

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
