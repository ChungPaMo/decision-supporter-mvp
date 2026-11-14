$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
Set-Location "$repoRoot/backend"
& "$repoRoot/.venv/Scripts/python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
exit $LASTEXITCODE
