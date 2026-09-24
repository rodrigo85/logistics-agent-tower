# =============================================================================
# scripts/setup.ps1 - One-shot local setup (Windows PowerShell)
#   1. finds Python >= 3.10        4. seeds the local SQLite database
#   2. creates .venv               5. runs the unit test suite
#   3. installs the package (-e) with dev extras + pre-commit hooks
# =============================================================================
param ([switch]$NoStart)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Test-Py($cmd, $args) {
    try { & $cmd @args -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>$null; return ($LASTEXITCODE -eq 0) } catch { return $false }
}

$py = $null; $pyArgs = @()
if ((Get-Command py -ErrorAction SilentlyContinue) -and (Test-Py "py" @("-3"))) { $py = "py"; $pyArgs = @("-3") }
elseif ((Get-Command python -ErrorAction SilentlyContinue) -and (Test-Py "python" @())) { $py = "python" }
if (-not $py) { Write-Host "[ERROR] Python 3.10+ not found. https://www.python.org/downloads/" -ForegroundColor Red; exit 1 }
Write-Host "[OK] Python: $py $pyArgs" -ForegroundColor Green

if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env"; Write-Host "[INFO] .env created from .env.example" }

if (-not (Test-Path ".venv\Scripts\python.exe")) { Write-Host "[1/4] Creating .venv" -ForegroundColor Yellow; & $py @pyArgs -m venv .venv }
$venvPy = Join-Path $Root ".venv\Scripts\python.exe"

Write-Host "[2/4] Installing package with dev extras" -ForegroundColor Yellow
& $venvPy -m pip install --upgrade pip --quiet
& $venvPy -m pip install -e ".[dev]"
try { & $venvPy -m pre_commit install | Out-Null } catch {}

Write-Host "[3/4] Seeding local database" -ForegroundColor Yellow
& $venvPy -m logistics_tower.db.seed

Write-Host "[4/4] Running unit tests" -ForegroundColor Yellow
& $venvPy -m pytest -m "not integration" -q
if ($LASTEXITCODE -ne 0) { Write-Host "[WARN] Some tests failed. Check the output above." -ForegroundColor Yellow }
else { Write-Host "`nSetup complete." -ForegroundColor Green }

if (-not $NoStart) {
    $resp = Read-Host "Start the dashboard now? (Y/N)"
    if ($resp -match "^[SsYy]") { & (Join-Path $Root "scripts\run.ps1") }
    else { Write-Host "Later: .\scripts\run.ps1  (or double-click scripts\run.bat)" -ForegroundColor Cyan }
}
