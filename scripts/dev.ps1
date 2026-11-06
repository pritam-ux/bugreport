# Starts MongoDB, the API on port 8100 and the frontend on port 5180. Press Ctrl+C to stop the API and frontend.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $env:LOCALAPPDATA 'BugSenseAI\venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'Run .\scripts\setup.ps1 first.' }

& (Join-Path $PSScriptRoot 'start-mongo.ps1')

$api = Start-Process -FilePath $python -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8100' `
    -WorkingDirectory (Join-Path $root 'backend') -PassThru -NoNewWindow
try {
    Write-Host 'API docs: http://localhost:8100/docs'
    Write-Host 'App:      http://localhost:5180'
    Push-Location (Join-Path $root 'frontend')
    npm run dev
}
finally {
    Pop-Location
    if (-not $api.HasExited) { Stop-Process -Id $api.Id -Force }
}
