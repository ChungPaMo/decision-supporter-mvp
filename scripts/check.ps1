$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
& ./.venv/Scripts/python.exe -m pytest --no-db -q --tb=short
if ($LASTEXITCODE) { throw 'pytest failed' }
& ./.venv/Scripts/python.exe -m pip check
if ($LASTEXITCODE) { throw 'Python dependency check failed' }
Push-Location frontend
try {
    npm run type-check; if ($LASTEXITCODE) { throw 'TypeScript check failed' }
    npm run build; if ($LASTEXITCODE) { throw 'Build failed' }
} finally { Pop-Location }
