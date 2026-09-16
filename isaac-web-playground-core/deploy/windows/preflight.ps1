# Run on the Windows box before anyone else needs the tool. Every check here
# corresponds to something that has actually gone wrong on this deployment.
param(
  [string]$Host_ = '127.0.0.1',
  [int]$WebPort = 8080,
  [int]$BridgePort = 8765,
  [string]$WslUser = $env:USERNAME
)

$fail = 0
function Check($name, [scriptblock]$test, $hint) {
  Write-Host -NoNewline ("  {0,-42}" -f $name)
  try {
    $result = & $test
    if ($result) { Write-Host "OK   $result" -ForegroundColor Green; return }
    Write-Host "FAIL" -ForegroundColor Red
  } catch {
    Write-Host "FAIL  $($_.Exception.Message)" -ForegroundColor Red
  }
  if ($hint) { Write-Host "        -> $hint" -ForegroundColor Yellow }
  $script:fail++
}

Write-Host "`nIsaac Playground preflight`n"

Check 'a desktop session exists (RTX needs one)' {
  $s = (query session 2>$null | Select-String 'Active')
  if ($s) { 'active session found' } else { $false }
} 'RDP in, or redirect to console with: tscon <id> /dest:console'

Check 'nvidia-smi responds' {
  $out = & nvidia-smi --query-gpu=index,name --format=csv,noheader 2>$null
  if ($LASTEXITCODE -eq 0) { ($out -join ' | ') } else { $false }
} 'The GPU driver is not answering; Isaac Sim will not render.'

Check 'bridge port is listening' {
  $c = Test-NetConnection -ComputerName 127.0.0.1 -Port $BridgePort -WarningAction SilentlyContinue
  if ($c.TcpTestSucceeded) { "tcp/$BridgePort" } else { $false }
} 'Start isaac.bat and wait for "[stage2] session ready".'

Check 'bridge reachable FROM WSL' {
  $r = wsl -u $WslUser -- bash -lc "gw=`$(ip route show default | awk '{print `$3; exit}'); (echo > /dev/tcp/`$gw/$BridgePort) 2>/dev/null && echo reachable || echo blocked"
  if ($r -match 'reachable') { 'via default gateway' } else { $false }
} 'This is the usual failure: the bridge binds 127.0.0.1, or the firewall blocks WSL. Use --host 0.0.0.0 and run setup-network.ps1.'

Check 'web page answers on localhost' {
  $r = Invoke-WebRequest "http://127.0.0.1:$WebPort/api/config" -UseBasicParsing -TimeoutSec 5
  if ($r.StatusCode -eq 200) { ($r.Content | ConvertFrom-Json).renderer } else { $false }
} 'Start web.bat; check the window for "command not found" (nvm not loaded).'

Check 'web page answers on the LAN address' {
  $r = Invoke-WebRequest "http://${Host_}:$WebPort/api/config" -UseBasicParsing -TimeoutSec 5
  if ($r.StatusCode -eq 200) { 'reachable' } else { $false }
} 'The listener is inside WSL. Run setup-network.ps1 as Administrator.'

Check 'a real frame comes out of the simulator' {
  $r = Invoke-WebRequest "http://127.0.0.1:$WebPort/api/frame.jpg" -UseBasicParsing -TimeoutSec 30
  if ($r.StatusCode -eq 200 -and $r.RawContentLength -gt 2000) { "$($r.RawContentLength) bytes $($r.Headers['Content-Type'])" } else { $false }
} 'This is the whole picture path. Check the Isaac window for a Replicator error.'

Check 'the shared upload directory exists both ways' {
  $win = Test-Path 'C:\playground\uploads'
  $wsl = wsl -u $WslUser -- bash -lc "test -d /mnt/c/playground/uploads && echo yes"
  if ($win -and $wsl -match 'yes') { 'both spellings resolve' } else { $false }
} 'mkdir C:\playground\uploads'

Write-Host ''
if ($script:fail -eq 0) { Write-Host "All checks passed." -ForegroundColor Green }
else { Write-Host "$($script:fail) check(s) failed." -ForegroundColor Red; exit 1 }
