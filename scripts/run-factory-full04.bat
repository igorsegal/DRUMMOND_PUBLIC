@echo off
setlocal
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-factory-full04.ps1"
set RC=%ERRORLEVEL%
echo.
pause
exit /b %RC%
