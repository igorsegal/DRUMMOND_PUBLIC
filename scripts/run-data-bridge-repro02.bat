@echo off
setlocal
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-data-bridge-repro02.ps1"
set RC=%ERRORLEVEL%
echo.
pause
exit /b %RC%
