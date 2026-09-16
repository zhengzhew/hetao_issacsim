param(
    [ValidateSet('All', 'Web', 'Bridge')][string]$Component = 'All',
    [string]$IsaacDir = 'D:\IsaacSim\6.0.1',
    [int]$WebPort = 8080,
    [int]$BridgePort = 8765,
    [string]$Scene = 'grid',
    [string]$Robot = 'jetbot'
)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$logDir = Join-Path $projectRoot 'logs'
$uploadDir = Join-Path $projectRoot 'uploads'
$runDir = Join-Path $projectRoot 'run'
New-Item -ItemType Directory -Force -Path $logDir,$uploadDir,$runDir | Out-Null

function Assert-PortFree([int]$Port) {
    $probe = [Net.Sockets.TcpClient]::new()
    try {
        $connected = $probe.ConnectAsync('127.0.0.1', $Port).Wait(500)
        if ($connected -and $probe.Connected) { throw "Port $Port already has a listener; inspect it before starting another process." }
    } catch [AggregateException] {
        # Connection refused means the port is available.
    } finally { $probe.Dispose() }
}

if ($Component -in @('All','Bridge')) {
    if (-not (Test-Path -LiteralPath (Join-Path $IsaacDir 'python.bat'))) {
        throw "Isaac Sim python.bat not found in $IsaacDir. Finish installing Isaac Sim first."
    }
    Assert-PortFree $BridgePort
}
if ($Component -in @('All','Web')) { Assert-PortFree $WebPort }

# Both processes share these settings and the same Windows upload directory.
$env:ISAAC_STREAM_RENDERER = 'mjpeg'
$env:ISAAC_BRIDGE_HOST = '127.0.0.1'
$env:ISAAC_BRIDGE_PORT = [string]$BridgePort
$env:ISAAC_UPLOAD_DIR = $uploadDir
$env:ISAAC_CATALOG_DIR = Join-Path $projectRoot 'configs'
if (-not $env:ISAAC_ASSET_ROOT) {
    $env:ISAAC_ASSET_ROOT = 'https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0'
}
$env:ISAAC_DEFAULT_SCENE = $Scene
$env:ISAAC_DEFAULT_ROBOT = $Robot
$env:ISAAC_CAPTURE_WIDTH = '640'
$env:ISAAC_CAPTURE_HEIGHT = '360'
$env:ISAAC_CAPTURE_FPS = '10'
$env:PORT = [string]$WebPort
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'

if ($Component -in @('All','Bridge')) {
    $pythonBat = Join-Path $IsaacDir 'python.bat'
    $entry = Join-Path $projectRoot 'bridge\isaac_playground.py'
    # Use a generated batch file to preserve spaces and Chinese paths.
    $batch = Join-Path $runDir 'bridge-native.cmd'
    $lines = @('@echo off','chcp 65001 >nul',
        ('call "{0}" "{1}" --host 127.0.0.1 --port {2} --no-livestream --no-multi-gpu --gpu 0 --idle-after 5 --idle-hz 5' -f $pythonBat,$entry,$BridgePort),
        'exit /b %errorlevel%')
    [IO.File]::WriteAllLines($batch,$lines,[Text.UTF8Encoding]::new($false))
    $bridgeProcess = Start-Process -FilePath $env:ComSpec -ArgumentList ('/d /s /c ""{0}""' -f $batch) -WorkingDirectory $IsaacDir -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir "bridge-$stamp.log") -RedirectStandardError (Join-Path $logDir "bridge-$stamp.err.log") -PassThru
    $bridgeProcess.Id | Set-Content (Join-Path $runDir 'bridge-native.pid')
    Write-Output "Bridge launcher PID=$($bridgeProcess.Id); logs=$logDir"
}
if ($Component -in @('All','Web')) {
    $nodeExe = (& node -p 'process.execPath').Trim()
    if (-not (Test-Path -LiteralPath $nodeExe)) { throw 'Cannot locate Node.js executable.' }
    $webProcess = Start-Process -FilePath $nodeExe -ArgumentList 'server/index.js' -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir "web-$stamp.log") -RedirectStandardError (Join-Path $logDir "web-$stamp.err.log") -PassThru
    $webProcess.Id | Set-Content (Join-Path $runDir 'web-native.pid')
    Write-Output "Web PID=$($webProcess.Id); URL=http://localhost:$WebPort"
}
