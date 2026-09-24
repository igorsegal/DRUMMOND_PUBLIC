@echo off
setlocal
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp016_INSTALL_VPS.ps1"
echo.
pause
