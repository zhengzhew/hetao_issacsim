param(
    [Parameter(Mandatory=$true)][ValidateSet('Start','Stop')][string]$Action,
    [Nullable[int]]$CaptureFps,
    [string]$IsaacDir = 'D:\IsaacSim\6.0.1',
    [string]$StreamHost = '',
    [string]$NodePath = '',
    [string]$StreamInterface = 'WLAN',
    [ValidateRange(10,900)][int]$WaitSeconds = 300,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$runDir = Join-Path $projectRoot 'run'
$platformDir = Join-Path $runDir 'platform'
$configuration = Join-Path $projectRoot 'configs\platform.json'
$serviceLock = $null
. (Join-Path $PSScriptRoot 'service-processes.ps1')
. (Join-Path $PSScriptRoot 'node-runtime.ps1')
try {
    New-Item -ItemType Directory -Force -Path $runDir,$platformDir | Out-Null
    $serviceLock = [IO.File]::Open((Join-Path $runDir 'service-control.lock'),'OpenOrCreate','ReadWrite','None')
    $config = Get-Content -LiteralPath $configuration -Raw -Encoding UTF8 | ConvertFrom-Json
    $owned = @(Get-NativeServiceProcesses -ProjectRoot $projectRoot -WebPort $config.port)
    $platform = @($owned | Where-Object Role -eq 'Platform')
    if ($Action -eq 'Stop' -or ($owned.Count -gt 0 -and $platform.Count -eq 0)) {
        if ($Action -eq 'Start') { Write-Host '正在将本项目旧服务切换到带配对验证的新入口……' }
        foreach ($entry in ($owned | Sort-Object @{Expression={switch ($_.Role) {'Platform'{0} 'Web'{1} 'BridgeLauncher'{2} default{3}}}})) {
            $current = Get-UnchangedServiceProcess -Snapshot $entry.Process
            if (-not $current) {continue}
            $saved = $ErrorActionPreference
            try {
                $ErrorActionPreference='Continue'
                $null = & "$env:SystemRoot\System32\taskkill.exe" /PID $current.ProcessId /T /F 2>&1
            } finally {$ErrorActionPreference=$saved}
            if (Get-UnchangedServiceProcess -Snapshot $entry.Process) {throw "无法关闭本项目进程 $($current.ProcessId)"}
        }
        if ($Action -eq 'Stop') {Write-Host '服务已关闭，仿真与网页均已停止。';exit 0}
    }
    if ($platform.Count -eq 0) {
        $node = Resolve-IsaacNode -RequestedPath $NodePath
        if (-not (Test-Path -LiteralPath (Join-Path $IsaacDir 'python.bat'))) {throw "未找到 Isaac Sim：$IsaacDir"}
        if (-not $StreamHost) {
            $adapter = [Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() | Where-Object {$_.Name -eq $StreamInterface -and $_.OperationalStatus -eq 'Up'} | Select-Object -First 1
            if ($adapter) {$StreamHost = @($adapter.GetIPProperties().UnicastAddresses | Where-Object {$_.Address.AddressFamily -eq 'InterNetwork'})[0].Address.ToString()}
            if (-not $StreamHost) {$StreamHost='127.0.0.1'}
        }
        $env:ISAAC_DIR=$IsaacDir
        $env:ISAAC_STREAM_HOST=$StreamHost
        $env:ISAAC_PLATFORM_CONFIG=$configuration
        if ($null -ne $CaptureFps) {if($CaptureFps -lt 1 -or $CaptureFps -gt 60){throw 'CaptureFps 必须为 1..60'};$env:ISAAC_STREAM_FPS=[string]$CaptureFps}
        $entry = Join-Path $projectRoot 'server\platform-main.js'
        $stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
        $process=Start-Process -FilePath $node -ArgumentList ('"{0}"' -f $entry) -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $platformDir "platform-$stamp.log") -RedirectStandardError (Join-Path $platformDir "platform-$stamp.err.log") -PassThru
        $process.Id | Set-Content (Join-Path $platformDir 'platform.pid')
    } else {Write-Host '管理入口已运行，不会重复启动。'}
    Write-Host '等待各体验台的网页、仿真和 WebRTC 信令就绪……'
    $deadline=(Get-Date).AddSeconds($WaitSeconds);$ready=$false;$lastNotice=[datetime]::MinValue
    do {
        if ($process -and $process.HasExited) {throw "管理入口已退出（$($process.ExitCode)），请查看 run/platform/platform-$stamp.err.log"}
        try {
            $health=Invoke-RestMethod -Uri "http://127.0.0.1:$($config.port)/health" -TimeoutSec 3
            $secrets=Get-Content -LiteralPath (Join-Path $platformDir 'access.json') -Raw -Encoding UTF8 | ConvertFrom-Json
            $ready=$health.ok -eq $true
            foreach($station in $config.stations){
                $state=Invoke-RestMethod -Uri "http://127.0.0.1:$($station.webPort)/api/status" -Headers @{'X-Isaac-Worker-Key'=$secrets.workerKey} -TimeoutSec 6
                $ready=$ready -and $state.bridge.connected -and $state.bridge.result.session.status -eq 'ready' -and $state.signaling.connected
            }
        }catch{$ready=$false}
        if($ready){break}
        if(((Get-Date)-$lastNotice).TotalSeconds -ge 15){Write-Host '实例仍在加载；详细状态保存在 run/platform 日志中。';$lastNotice=Get-Date}
        Start-Sleep -Seconds 2
    }while((Get-Date)-lt $deadline)
    if(-not $ready){throw '等待就绪超时。请查看 run/platform 日志；不会把信令连接当作视频播放成功。'}
    Write-Host "服务已就绪：http://localhost:$($config.port)/"
    if($StreamHost){Write-Host "局域网入口：http://${StreamHost}:$($config.port)/"}
    Write-Host "老师首次密码：$platformDir\teacher-password.txt"
    if($config.localConnector.enabled -and -not $config.publicOrigin){Write-Host '体验浏览器仍需配对；同一 WLAN 子网内的新版机械臂连接器选配置即可连接。'}
    else{Write-Host '老师登录后生成浏览器和采集器配对码；旧版采集器需更新。'}
    Write-Host '实际视频播放在浏览器确认。'
    if(-not $NoBrowser){Start-Process "http://localhost:$($config.port)/"}
}catch{Write-Host ("操作未完成："+$_.Exception.Message);exit 1}
finally{if($serviceLock){$serviceLock.Dispose()}}
