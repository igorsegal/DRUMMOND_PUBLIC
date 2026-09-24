@echo off
setlocal
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0collect-mt4-equivalence01.ps1" -Push
set RC=%ERRORLEVEL%
echo.
if %RC%==0 (
  echo MT4 EQUIVALENCE 01 LOCAL PASS
) else (
  echo MT4 EQUIVALENCE 01 produced a mismatch report and pushed it to GitHub.
)
pause
exit /b %RC%
