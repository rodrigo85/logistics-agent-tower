@echo off
:: scripts/run.bat - double-click launcher for Windows (delegates to run.ps1)
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1"
