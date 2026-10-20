function Resolve-IsaacNode {
    param([string]$RequestedPath = '')
    if ($RequestedPath) {
        $resolved = (Resolve-Path -LiteralPath $RequestedPath -ErrorAction Stop).Path
    } else {
        # Reuse the standalone installation used by the existing LAN firewall rule.
        $installed = Join-Path $env:LOCALAPPDATA 'Programs\nodejs\node.exe'
        $resolved = if (Test-Path -LiteralPath $installed) {$installed} else {(Get-Command node.exe -ErrorAction Stop).Source}
    }
    $versionText = & $resolved --version
    if ($LASTEXITCODE -ne 0 -or [version]($versionText.Trim().TrimStart('v')) -lt [version]'20.11') {throw 'Node.js 20.11 or newer is required.'}
    return $resolved
}
