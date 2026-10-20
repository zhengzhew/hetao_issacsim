param([string]$IsaacDir = 'D:\IsaacSim\6.0.1')
$ErrorActionPreference = 'Stop'
$challengeRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$isaacPython = Join-Path $IsaacDir 'python.bat'
if (-not (Test-Path -LiteralPath $isaacPython)) { throw "Isaac Sim Python not found: $isaacPython" }
& $isaacPython (Join-Path $challengeRoot 'scripts\fetch_challenge_assets.py')
if ($LASTEXITCODE -ne 0) { throw 'Challenge asset download failed' }
& $isaacPython -m pip install --no-deps --target (Join-Path $challengeRoot 'run\python-deps') onnxruntime==1.22.1
if ($LASTEXITCODE -ne 0) { throw 'ONNX Runtime setup failed' }
Write-Output 'Challenge assets and local runtime are ready. Start with start-native.ps1.'
