# scripts/run.ps1 - Start the API + dashboard in a dedicated window (Windows PowerShell)
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { Write-Host "[ERROR] .venv not found. Run .\scripts\setup.ps1 first." -ForegroundColor Red; exit 1 }

# Free port 8000 if a previous instance is still listening
$old = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($old -and $old.OwningProcess -gt 4) { Stop-Process -Id $old.OwningProcess -Force -ErrorAction SilentlyContinue; Start-Sleep -Seconds 1 }

Write-Host "Logistics Agent Tower -> http://localhost:8000  (Swagger: /docs)" -ForegroundColor Cyan
$proc = Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location $Root; & $venvPy -m uvicorn logistics_tower.api.main:app --host 127.0.0.1 --port 8000" -PassThru
Start-Sleep -Seconds 2
try { Start-Process "http://localhost:8000" } catch {}
Write-Host "[OK] Server started (PID $($proc.Id))." -ForegroundColor Green
