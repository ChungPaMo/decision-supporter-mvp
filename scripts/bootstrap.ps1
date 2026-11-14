$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path .venv/Scripts/python.exe)) {
    python -m venv .venv
    if ($LASTEXITCODE) { throw 'Virtual environment creation failed' }
}
& ./.venv/Scripts/python.exe -m pip install -c infrastructure/python-constraints.txt -r backend/requirements-forecast.txt
if ($LASTEXITCODE) { throw 'Python dependency installation failed' }
Push-Location frontend
try { npm ci; if ($LASTEXITCODE) { throw 'npm ci failed' } } finally { Pop-Location }
