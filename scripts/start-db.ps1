$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
Set-Location $repoRoot
if (-not (Test-Path .env)) { throw 'Run scripts/init-env.ps1 first.' }
docker info --format '{{.ServerVersion}}'
if ($LASTEXITCODE) { throw 'Docker engine unavailable' }
$containers = docker ps -a --format '{{.Names}}'
if ($LASTEXITCODE) { throw 'Unable to inspect containers' }
$volumes = docker volume ls --format '{{.Name}}'
if ($LASTEXITCODE) { throw 'Unable to inspect volumes' }
$networks = docker network ls --format '{{.Name}}'
if ($LASTEXITCODE) { throw 'Unable to inspect Docker resources' }
if ($containers -contains 'chungpamo-monorepo-db' -or $volumes -contains 'chungpamo-monorepo-pgdata' -or $networks -contains 'chungpamo-monorepo-net') {
    throw 'Dedicated resource already exists. Inspect its ownership before any restart; this script refuses automatic reuse.'
}
if (Get-NetTCPConnection -LocalPort 55433 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 55433 occupied' }
docker compose --env-file .env -f infrastructure/compose.yaml config --quiet
if ($LASTEXITCODE) { throw 'Compose configuration invalid' }
docker compose --env-file .env -f infrastructure/compose.yaml up -d --wait db
if ($LASTEXITCODE) { throw 'Dedicated DB startup/health failed; resources preserved' }
