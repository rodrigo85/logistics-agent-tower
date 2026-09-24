@echo off
:: scripts/setup.bat - double-click installer for Windows (delegates to setup.ps1)
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
pause
