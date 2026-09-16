# Run once, as Administrator. Re-run after a WSL rebuild (the WSL IP changes).
#
# Two separate problems are solved here:
#   1. The Node server listens on 0.0.0.0 *inside the WSL network namespace*.
#      WSL2's localhostForwarding only forwards from the Windows loopback, so
#      without a portproxy nobody on the LAN can reach the page at all.
#   2. The bridge listens on Windows and must be reachable *from* WSL.
#
# Verified on this box: pointing the portproxy at 127.0.0.1 works only
# sometimes; the WSL address is the reliable target.

param(
  [int]$WebPort = 8080,
  [int]$BridgePort = 8765,
  [string]$WslUser = $env:USERNAME
)

$ErrorActionPreference = 'Stop'

$wslIp = (wsl -u $WslUser -- bash -lc "ip -4 -o addr show eth0 | awk '{print `$4}' | cut -d/ -f1").Trim()
if (-not $wslIp) { throw 'Could not determine the WSL address. Is WSL running?' }
Write-Host "WSL address: $wslIp"

netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=$WebPort 2>$null | Out-Null
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=$WebPort connectaddress=$wslIp connectport=$WebPort
Write-Host "portproxy: 0.0.0.0:$WebPort -> ${wslIp}:$WebPort"

function Set-Rule($name, $protocol, $ports) {
  Remove-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue
  New-NetFirewallRule -DisplayName $name -Direction Inbound -Protocol $protocol -LocalPort $ports -Action Allow | Out-Null
  Write-Host "firewall: $name ($protocol $($ports -join ','))"
}

Set-Rule 'Isaac Playground Web'   'TCP' $WebPort
Set-Rule 'Isaac Playground Bridge' 'TCP' $BridgePort
# Omniverse streaming needs far more than the two ports the docs mention.
# Only relevant if isaac.bat is started with --livestream.
Set-Rule 'Omniverse Streaming TCP' 'TCP' @('47995-48012','49000-49007','49100')
Set-Rule 'Omniverse Streaming UDP' 'UDP' @('47995-48012','49000-49007','49100')

Write-Host ''
netsh interface portproxy show v4tov4
