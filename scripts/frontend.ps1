Set-Location "$(Split-Path $PSScriptRoot -Parent)/frontend"
npm run dev
exit $LASTEXITCODE
