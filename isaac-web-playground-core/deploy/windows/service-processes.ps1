# Shared by the local service controller. All matches are scoped to this checkout.
function Test-ServiceCommandPath {
    param([string]$CommandLine, [string]$ExpectedPath)
    foreach ($token in [regex]::Matches($CommandLine, '"([^"]+)"|([^\s"]+)')) {
        $value = if ($token.Groups[1].Success) { $token.Groups[1].Value } else { $token.Groups[2].Value }
        if ($value.Replace('/', '\') -ieq $ExpectedPath.Replace('/', '\')) { return $true }
    }
    return $false
}

function Get-NativeServiceProcesses {
    param([string]$ProjectRoot, [int]$WebPort = 8080)
    $items = @(Get-CimInstance Win32_Process -Filter "Name = 'cmd.exe' OR Name = 'node.exe' OR Name = 'kit.exe' OR Name = 'python.exe' OR Name = 'pythonw.exe'")
    $platformEntry = Join-Path $ProjectRoot 'server\platform-main.js'
    $webEntry = Join-Path $ProjectRoot 'server\index.js'
    $bridgeEntry = Join-Path $ProjectRoot 'bridge\isaac_playground.py'
    $launcher = Join-Path $ProjectRoot 'run\bridge-native.cmd'
    $legacyPid = 0
    $pidFile = Join-Path $ProjectRoot 'run\web-native.pid'
    if (Test-Path -LiteralPath $pidFile) {
        [void][int]::TryParse(([string](Get-Content -LiteralPath $pidFile -Raw)).Trim(), [ref]$legacyPid)
    }
    foreach ($item in $items) {
        $role = $null
        if ($item.Name -eq 'node.exe' -and (Test-ServiceCommandPath $item.CommandLine $platformEntry)) {
            $role = 'Platform'
        } elseif ($item.Name -eq 'cmd.exe' -and (Test-ServiceCommandPath $item.CommandLine $launcher)) {
            $role = 'BridgeLauncher'
        } elseif ($item.Name -in @('kit.exe','python.exe','pythonw.exe') -and (Test-ServiceCommandPath $item.CommandLine $bridgeEntry)) {
            $role = 'Bridge'
        } elseif ($item.Name -eq 'node.exe' -and (Test-ServiceCommandPath $item.CommandLine $webEntry)) {
            $role = 'Web'
        } elseif ($item.Name -eq 'node.exe' -and $item.ProcessId -eq $legacyPid -and
                  $item.CommandLine -match '^(?:"[^"]+"|\S+)\s+"?server[/\\]index\.js"?\s*$') {
            # The old launcher used a relative entry. A PID alone is not proof of ownership.
            $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $WebPort -ErrorAction SilentlyContinue)
            $ownedPort = @($listeners | Where-Object { $_.OwningProcess -eq $item.ProcessId }).Count -gt 0
            $assets = $null
            if ($ownedPort) {
                try { $assets = Invoke-RestMethod -Uri "http://127.0.0.1:$WebPort/api/assets" -TimeoutSec 5 } catch {}
            }
            $expectedUploads = Join-Path $ProjectRoot 'uploads'
            if ($ownedPort -and $assets.ok -and ([string]$assets.dir).Replace('/', '\').TrimEnd('\') -ieq $expectedUploads) {
                $role = 'Web'
            } else {
                throw "Cannot verify legacy Node process $legacyPid. Inspect its command line and project before stopping it."
            }
        }
        if ($role) { [pscustomobject]@{ Role = $role; Process = $item } }
    }
}

function Get-UnchangedServiceProcess {
    param($Snapshot)
    # CIM can briefly retain a terminated child after taskkill /T has stopped its parent.
    try {
        $live = Get-Process -Id $Snapshot.ProcessId -ErrorAction Stop
        if ($live.HasExited) { return $null }
    } catch [Microsoft.PowerShell.Commands.ProcessCommandException] { return $null }
    $current = Get-CimInstance Win32_Process -Filter "ProcessId = $($Snapshot.ProcessId)"
    if (-not $current) { return $null }
    if ($current.CreationDate -ne $Snapshot.CreationDate -or $current.CommandLine -cne $Snapshot.CommandLine) {
        throw "PID $($Snapshot.ProcessId) has changed identity; it will not be stopped."
    }
    return $current
}
