# Installs PhotoCraft (MSI) from the official GitHub release, after verifying its SHA-256 checksum.
. "$PSScriptRoot\..\common-script.ps1"
Assert-Admin
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$arch = switch (Get-Arch) { 'x86_64' { 'x64' } 'aarch64' { 'arm64' } }
$api = if ($env:PHOTOCRAFT_API) { $env:PHOTOCRAFT_API } else { 'https://api.github.com/repos/storytold/photocraft/releases/latest' }

Write-Info 'Looking up the latest PhotoCraft release...'
$rel = Invoke-RestMethod $api -Headers @{ 'User-Agent' = 'xutil' }
$msi = $rel.assets | Where-Object { $_.name -match "^photocraft-.*-windows-$arch\.msi$" } | Select-Object -First 1
$sum = $rel.assets | Where-Object { $_.name -eq 'SHA256SUMS.txt' } | Select-Object -First 1
if (-not $msi -or -not $sum) { Write-Fail 'Could not find the MSI or SHA256SUMS.txt in the latest release.'; exit 1 }

$tmp = Join-Path $env:TEMP ('photocraft_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $tmp | Out-Null
try {
    $file = Join-Path $tmp $msi.name
    $sumFile = Join-Path $tmp 'SHA256SUMS.txt'
    Write-Warn "Downloading $($msi.name)"
    Invoke-WebRequest $msi.browser_download_url -OutFile $file
    Invoke-WebRequest $sum.browser_download_url -OutFile $sumFile

    $expected = Get-Content $sumFile | ForEach-Object {
        $p = $_ -split '\s+'
        if ($p.Count -ge 2 -and $p[1].TrimStart('*') -eq $msi.name) { $p[0] }
    } | Select-Object -First 1
    $actual = (Get-FileHash $file -Algorithm SHA256).Hash
    if (-not $expected -or $expected -ne $actual) { Write-Fail 'Checksum verification FAILED. Nothing was installed.'; exit 1 }
    Write-Ok 'Checksum OK'

    $p = Start-Process msiexec.exe -ArgumentList "/i `"$file`" /passive /norestart" -Wait -PassThru
    if ($p.ExitCode -notin 0, 3010) { Write-Fail "Installer failed (exit $($p.ExitCode))"; exit $p.ExitCode }
    Write-Ok 'PhotoCraft installed. Open it from the Start menu.'
    Write-Warn 'PhotoCraft is early alpha software. Keep backups of your originals.'
} finally {
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
