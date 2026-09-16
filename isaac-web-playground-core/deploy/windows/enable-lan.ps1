param(
    [string]$InterfaceAlias = 'WLAN',
    [string]$NodePath = 'C:\Users\hetao\AppData\Local\Programs\nodejs\node.exe'
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $NodePath)) { throw 'Node.js executable was not found.' }
if (-not (Get-NetAdapter -Name $InterfaceAlias -ErrorAction SilentlyContinue)) { throw 'Network adapter was not found.' }
$ruleName = 'Hetao-IsaacSim-Web-LAN-8080'
if (-not (Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name $ruleName -DisplayName 'Hetao Isaac Sim Web (LAN 8080)' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8080 -RemoteAddress LocalSubnet -InterfaceAlias $InterfaceAlias -Program $NodePath -Profile Any | Out-Null
}
$rule = Get-NetFirewallRule -Name $ruleName
$rule | Select-Object Name,Enabled,Direction,Action
$rule | Get-NetFirewallAddressFilter | Select-Object RemoteAddress
$rule | Get-NetFirewallPortFilter | Select-Object Protocol,LocalPort
