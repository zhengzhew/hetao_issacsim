param(
    [string]$InterfaceAlias = 'WLAN',
    [string]$KitPath = 'D:\IsaacSim\6.0.1\kit\python\kit.exe'
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $KitPath)) { throw 'Isaac Sim Kit executable not found.' }
if (-not (Get-NetAdapter -Name $InterfaceAlias -ErrorAction SilentlyContinue)) { throw 'Network adapter not found.' }
foreach ($entry in @(
    @{Name='Hetao-IsaacSim-WebRTC-LAN-49100'; Protocol='TCP'; Port=49100},
    @{Name='Hetao-IsaacSim-WebRTC-LAN-47998'; Protocol='UDP'; Port=47998}
)) {
    $rule = Get-NetFirewallRule -Name $entry.Name -ErrorAction SilentlyContinue
    if ($rule) {
        Set-NetFirewallRule -Name $entry.Name -Enabled True -Direction Inbound -Action Allow -Protocol $entry.Protocol -LocalPort $entry.Port -RemoteAddress LocalSubnet -InterfaceAlias $InterfaceAlias -Program $KitPath -Profile Any
    } else {
        New-NetFirewallRule -Name $entry.Name -DisplayName $entry.Name -Enabled True -Direction Inbound -Action Allow -Protocol $entry.Protocol -LocalPort $entry.Port -RemoteAddress LocalSubnet -InterfaceAlias $InterfaceAlias -Program $KitPath -Profile Any | Out-Null
    }
}
