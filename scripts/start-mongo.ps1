# Starts a private MongoDB for BugSense AI on port 27018, without Docker or admin rights.
# Binaries and data live in %LOCALAPPDATA%\BugSenseAI, because live database files inside
# OneDrive get locked by sync. Any other MongoDB also works: set MONGODB_URI in backend\.env.
$ErrorActionPreference = 'Stop'
$runtime = Join-Path $env:LOCALAPPDATA 'BugSenseAI'
$port = 27018
$version = '8.0.15'

$listening = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($listening) {
    Write-Host "MongoDB is already listening on port $port."
    exit 0
}

$mongod = Join-Path $runtime "mongodb\mongodb-win32-x86_64-windows-$version\bin\mongod.exe"
if (-not (Test-Path $mongod)) {
    $zip = Join-Path $runtime 'mongodb.zip'
    $url = "https://fastdl.mongodb.org/windows/mongodb-windows-x86_64-$version.zip"
    New-Item -ItemType Directory -Force (Join-Path $runtime 'mongodb') | Out-Null
    Write-Host "Downloading MongoDB $version (about 600 MB)..."
    $ProgressPreference = 'SilentlyContinue'
    Invoke-WebRequest -Uri $url -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath (Join-Path $runtime 'mongodb') -Force
    Remove-Item $zip
}

$data = Join-Path $runtime 'mongo-data'
New-Item -ItemType Directory -Force $data | Out-Null
Start-Process -FilePath $mongod -WindowStyle Hidden -ArgumentList @(
    '--dbpath', "`"$data`"", '--port', $port, '--bind_ip', '127.0.0.1',
    '--logpath', "`"$(Join-Path $runtime 'mongod.log')`"", '--logappend'
)

foreach ($attempt in 1..30) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        Write-Host "MongoDB is running on port $port."
        exit 0
    }
    Start-Sleep -Seconds 1
}
throw "MongoDB did not start. See $(Join-Path $runtime 'mongod.log')"
