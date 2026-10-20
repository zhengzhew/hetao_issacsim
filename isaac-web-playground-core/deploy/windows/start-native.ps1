param(
    [ValidateSet('All', 'Web', 'Bridge')][string]$Component = 'All',
    [string]$IsaacDir = 'D:\IsaacSim\6.0.1',
    [int]$WebPort = 8080,
    [int]$BridgePort = 8765,
    [string]$Scene = 'challenge-arm',
    [string]$Robot = 'so101',
    [ValidateRange(320,1920)][int]$CaptureWidth = 1920,
    [ValidateRange(240,1080)][int]$CaptureHeight = 1080,
    [ValidateRange(1,60)][int]$CaptureFps = 60,
    [ValidateRange(20,95)][int]$CaptureQuality = 90,
    [ValidateSet('mjpeg','native')][string]$Renderer = 'native',
    [string]$StreamHost = '',
    [string]$StreamInterface = 'WLAN'
)
$ErrorActionPreference = 'Stop'
if (-not $StreamHost) {
    $adapter = [Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() |
        Where-Object { $_.Name -eq $StreamInterface -and $_.OperationalStatus -eq 'Up' }
    $addresses = @($adapter | ForEach-Object { $_.GetIPProperties().UnicastAddresses } |
        Where-Object { $_.Address.AddressFamily -eq 'InterNetwork' -and $_.Address.ToString() -notlike '169.254.*' })
    if ($addresses.Count -ne 1) {
        throw 'Cannot select one LAN IPv4 address. Specify -StreamHost <server-IP>, or 127.0.0.1 for local-only use.'
    }
    $StreamHost = $addresses[0].Address.ToString()
}
Write-Output "WebRTC stream host: $StreamHost"
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
if ($Renderer -eq 'native' -and $Component -in @('All','Web') -and
    -not (Test-Path -LiteralPath (Join-Path $projectRoot 'web\native-sdk.js'))) {
    throw 'WebRTC client bundle missing. Run npm ci and npm run build:native in the project directory first.'
}

# Resolve Node before starting Isaac, including common installations outside Explorer's PATH.
if ($Component -in @('All','Web')) {
    $nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
    $nodeExe = if ($nodeCommand) { $nodeCommand.Source } else { $null }
    if (-not $nodeExe) {
        $candidates = @(
            (Join-Path $env:ProgramFiles 'nodejs\node.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\nodejs\node.exe'),
            (Join-Path $env:USERPROFILE '.codearts\runtimes\node\node.exe')
        )
        $nodeExe = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
    if (-not $nodeExe) { throw 'Cannot locate Node.js. Install Node.js before starting services.' }
}

# Both processes share these settings and the same Windows upload directory.
$env:ISAAC_STREAM_RENDERER = $Renderer
$env:ISAAC_STREAM_HOST = $StreamHost
$env:ISAAC_PUBLIC_IP = $StreamHost
$env:ISAAC_STREAM_WIDTH = [string]$CaptureWidth
$env:ISAAC_STREAM_HEIGHT = [string]$CaptureHeight
$env:ISAAC_STREAM_FPS = [string]$CaptureFps
$env:ISAAC_BRIDGE_HOST = '127.0.0.1'
$env:ISAAC_BRIDGE_PORT = [string]$BridgePort
$env:ISAAC_UPLOAD_DIR = $uploadDir
$env:ISAAC_CATALOG_DIR = Join-Path $projectRoot 'configs'
if (-not $env:ISAAC_ASSET_ROOT) {
    $env:ISAAC_ASSET_ROOT = 'https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0'
}
$env:ISAAC_DEFAULT_SCENE = $Scene
$env:ISAAC_DEFAULT_ROBOT = $Robot
$env:ISAAC_CAPTURE_WIDTH = [string]$CaptureWidth
$env:ISAAC_CAPTURE_HEIGHT = [string]$CaptureHeight
$env:ISAAC_CAPTURE_FPS = [string]$CaptureFps
$env:ISAAC_CAPTURE_QUALITY = [string]$CaptureQuality
# Keep the unused headless viewport small; Replicator renders the stream
# independently at CaptureWidth/CaptureHeight, as in the measured setup.
$env:ISAAC_RENDER_WIDTH = '640'
$env:ISAAC_RENDER_HEIGHT = '360'
if ($Renderer -eq 'native') {
    $env:ISAAC_RENDER_WIDTH = [string]$CaptureWidth
    $env:ISAAC_RENDER_HEIGHT = [string]$CaptureHeight
}
$env:PORT = [string]$WebPort
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'

if ($Component -in @('All','Bridge')) {
    $pythonBat = Join-Path $IsaacDir 'python.bat'
    $entry = Join-Path $projectRoot 'bridge\isaac_playground.py'
    # Use a generated batch file to preserve spaces and Chinese paths.
    $batch = Join-Path $runDir 'bridge-native.cmd'
    $streamArgs = if ($Renderer -eq 'native') { '--livestream --hide-ui --idle-after 0' } else { '--no-livestream --idle-after 5' }
    $lines = @('@echo off','chcp 65001 >nul',
        ('call "{0}" "{1}" --host 127.0.0.1 --port {2} {3} --no-multi-gpu --gpu 0 --idle-hz 5' -f $pythonBat,$entry,$BridgePort,$streamArgs),
        'exit /b %errorlevel%')
    [IO.File]::WriteAllLines($batch,$lines,[Text.UTF8Encoding]::new($false))
    $bridgeProcess = Start-Process -FilePath $env:ComSpec -ArgumentList ('/d /s /c ""{0}""' -f $batch) -WorkingDirectory $IsaacDir -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir "bridge-$stamp.log") -RedirectStandardError (Join-Path $logDir "bridge-$stamp.err.log") -PassThru
    $bridgeProcess.Id | Set-Content (Join-Path $runDir 'bridge-native.pid')
    Write-Output "Bridge launcher PID=$($bridgeProcess.Id); logs=$logDir"
}
if ($Component -in @('All','Web')) {
    $webProcess = Start-Process -FilePath $nodeExe -ArgumentList ('"{0}"' -f (Join-Path $projectRoot 'server\index.js')) -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir "web-$stamp.log") -RedirectStandardError (Join-Path $logDir "web-$stamp.err.log") -PassThru
    $webProcess.Id | Set-Content (Join-Path $runDir 'web-native.pid')
    Write-Output "Web PID=$($webProcess.Id); URL=http://localhost:$WebPort"
}
