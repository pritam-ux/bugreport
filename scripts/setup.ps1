# One-time setup on Windows: Python packages, frontend packages, MongoDB, models and sample data.
# Safe to run again. It keeps existing data and an existing backend\.env.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $env:LOCALAPPDATA 'BugSenseAI'
$venv = Join-Path $runtime 'venv'
$python = Join-Path $venv 'Scripts\python.exe'

New-Item -ItemType Directory -Force $runtime | Out-Null
if (-not (Test-Path $python)) {
    Write-Host 'Creating the Python environment...'
    python -m venv $venv
}
Write-Host 'Installing Python packages...'
& $python -m pip install --quiet --upgrade pip
& $python -m pip install --quiet -r (Join-Path $root 'backend\requirements-dev.txt')
if ($LASTEXITCODE -ne 0) { throw 'Installing Python packages failed.' }

$envFile = Join-Path $root 'backend\.env'
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $root 'backend\.env.example') $envFile
    Write-Host 'Created backend\.env.'
}

Write-Host 'Installing frontend packages...'
Push-Location (Join-Path $root 'frontend')
npm install --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { Pop-Location; throw 'npm install failed.' }
Pop-Location

& (Join-Path $PSScriptRoot 'start-mongo.ps1')

Push-Location (Join-Path $root 'backend')
Write-Host 'Loading sample data...'
& $python -m scripts.seed
Pop-Location

Write-Host ''
Write-Host 'Setup finished. Start the app with: .\scripts\dev.ps1'
