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
Write-Host 'Installing Python packages (CPU-only PyTorch, about 1 GB in total)...'
& $python -m pip install --quiet --upgrade pip
& $python -m pip install --quiet torch --index-url https://download.pytorch.org/whl/cpu
& $python -m pip install --quiet -r (Join-Path $root 'backend\requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Installing Python packages failed.' }

$envFile = Join-Path $root 'backend\.env'
if (-not (Test-Path $envFile)) {
    $secret = & $python -c "import secrets; print(secrets.token_urlsafe(48))"
    (Get-Content (Join-Path $root 'backend\.env.example')) -replace '^JWT_SECRET=$', "JWT_SECRET=$secret" |
        Set-Content $envFile -Encoding utf8
    Write-Host 'Created backend\.env with a new JWT secret.'
}

Write-Host 'Installing frontend packages...'
Push-Location (Join-Path $root 'frontend')
npm install --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { Pop-Location; throw 'npm install failed.' }
Pop-Location

& (Join-Path $PSScriptRoot 'start-mongo.ps1')

Push-Location (Join-Path $root 'backend')
Write-Host 'Training the models (the first run downloads a 90 MB embedding model)...'
& $python -m scripts.train
if ($LASTEXITCODE -ne 0) { Pop-Location; throw 'Training failed.' }
Write-Host 'Loading sample data...'
& $python -m scripts.seed
Pop-Location

Write-Host ''
Write-Host 'Setup finished. Start the app with: .\scripts\dev.ps1'
