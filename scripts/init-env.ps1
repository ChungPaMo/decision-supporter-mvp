$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$target = Join-Path $repoRoot '.env'
if (Test-Path -LiteralPath $target) { throw 'Existing .env preserved; edit it manually.' }
function New-DevPassword {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return ([BitConverter]::ToString($bytes)).Replace('-', '').ToLowerInvariant()
}
$adminPassword = New-DevPassword
$appPassword = New-DevPassword
$content = @"
POSTGRES_ADMIN_USER=chungpamo_admin
POSTGRES_ADMIN_PASSWORD=$adminPassword
APP_DB_USER=chungpamo_app
APP_DB_PASSWORD=$appPassword
DATABASE_URL=postgresql+psycopg://chungpamo_app:$appPassword@127.0.0.1:55433/chungpamo
PERSISTENCE=postgres
CORS_ALLOW_ORIGINS=http://127.0.0.1:5173
"@
[IO.File]::WriteAllText($target, $content, (New-Object Text.UTF8Encoding($false)))
Write-Output 'Created local-only .env with random development passwords; no values printed.'
