param(
    [int]$DownloadProcessId = 0,
    [string]$Archive = 'D:\IsaacSim\downloads\isaac-sim-standalone-6.0.1-windows-x86_64.zip',
    [string]$Destination = 'D:\IsaacSim\6.0.1'
)
$ErrorActionPreference = 'Stop'
$expectedBytes = 10600096696L
$expectedMD5 = 'c7fa3a830b251f10305cd7883039df9b'
# The checksum is published on NVIDIA's 6.0.1 download page.
# Waiting on the actual process avoids extracting a still-growing archive.
if ($DownloadProcessId -gt 0) {
    $download = Get-Process -Id $DownloadProcessId -ErrorAction SilentlyContinue
    if ($download) {
        if ($download.ProcessName -ne 'curl') { throw 'Download PID belongs to a different program.' }
        while (-not $download.WaitForExit(30000)) {
            $bytes = (Get-Item -LiteralPath $Archive).Length
            Write-Output ("Downloading: {0:N1}% ({1:N2} GiB)" -f (100*$bytes/$expectedBytes),($bytes/1GB))
        }
        $download.Dispose()
    }
}
$file = Get-Item -LiteralPath $Archive
if ($file.Length -ne $expectedBytes) { throw "Incomplete archive: $($file.Length) / $expectedBytes bytes. Resume the download before installing." }
Write-Output 'Checking official MD5 checksum...'
$actualHash = (Get-FileHash -LiteralPath $Archive -Algorithm MD5).Hash.ToLowerInvariant()
if ($actualHash -ne $expectedMD5) { throw "Archive checksum mismatch: $actualHash" }
Write-Output "Checksum verified: $actualHash"
if ((Test-Path -LiteralPath $Destination) -and (Get-ChildItem -LiteralPath $Destination -Force | Select-Object -First 1)) {
    throw 'Installation directory is not empty; inspect it before continuing. Nothing was overwritten.'
}
New-Item -ItemType Directory -Path $Destination -Force | Out-Null
Write-Output "Extracting to $Destination..."
& tar.exe -xf $Archive -C $Destination
if ($LASTEXITCODE -ne 0) { throw "Extraction failed: exit $LASTEXITCODE" }
if (-not (Test-Path -LiteralPath (Join-Path $Destination 'python.bat'))) { throw 'Extraction finished but python.bat is missing at the installation root.' }
Write-Output 'Archive verified and extracted. Post-install and real simulation checks are still required.'
