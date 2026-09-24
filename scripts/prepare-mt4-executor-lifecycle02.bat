@echo off
setlocal
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0prepare-mt4-executor-lifecycle02.ps1"
set RC=%ERRORLEVEL%
echo.
pause
exit /b %RC%
