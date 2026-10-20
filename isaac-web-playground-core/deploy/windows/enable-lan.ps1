param(
    [string]$InterfaceAlias = 'WLAN',
    [string]$NodePath = ''
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'node-runtime.ps1')
$NodePath = Resolve-IsaacNode -RequestedPath $NodePath
$platformConfig = Get-Content -LiteralPath (Join-Path $PSScriptRoot '..\..\configs\platform.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not (Test-Path -LiteralPath $NodePath)) { throw 'Node.js executable was not found.' }
if (-not (Get-NetAdapter -Name $InterfaceAlias -ErrorAction SilentlyContinue)) { throw 'Network adapter was not found.' }
$ruleName = 'Hetao-IsaacSim-Web-LAN-8080'
if (-not (Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name $ruleName -DisplayName 'Hetao Isaac Sim Web (LAN 8080)' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $platformConfig.port -RemoteAddress LocalSubnet -InterfaceAlias $InterfaceAlias -Program $NodePath -Profile Any | Out-Null
} else {
    Set-NetFirewallRule -Name $ruleName -Enabled True -Direction Inbound -Action Allow -Protocol TCP -LocalPort $platformConfig.port -RemoteAddress LocalSubnet -InterfaceAlias $InterfaceAlias -Program $NodePath -Profile Any
}
$rule = Get-NetFirewallRule -Name $ruleName
$rule | Select-Object Name,Enabled,Direction,Action
$rule | Get-NetFirewallAddressFilter | Select-Object RemoteAddress
$rule | Get-NetFirewallPortFilter | Select-Object Protocol,LocalPort
