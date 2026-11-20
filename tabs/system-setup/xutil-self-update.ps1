# Refresh the installed xutil from the downloaded source folder.
# Override the source location with $env:XUTIL_SOURCE_DIR.
$src = $env:XUTIL_SOURCE_DIR
if (-not $src) { $src = Join-Path $env:USERPROFILE 'Downloads\xutil' }
$installer = Join-Path $src 'install.ps1'
if (-not (Test-Path $installer)) {
    Write-Error "Cannot find xutil source at $src. Set XUTIL_SOURCE_DIR to the folder that contains install.ps1."
    exit 1
}
Write-Host "Updating xutil from $src" -ForegroundColor Cyan
& $installer
