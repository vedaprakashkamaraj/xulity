. "$PSScriptRoot\..\common-script.ps1"
$key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced'
$backupDir = Join-Path $env:USERPROFILE 'xutil-backup'
New-Item -ItemType Directory -Force $backupDir | Out-Null
$old = Get-ItemProperty $key | Select-Object HideFileExt, Hidden
$old | ConvertTo-Json | Set-Content (Join-Path $backupDir 'explorer-advanced.json')
Write-Info "Previous values saved to $backupDir\explorer-advanced.json"
Set-ItemProperty $key -Name HideFileExt -Value 0
Set-ItemProperty $key -Name Hidden -Value 1
$answer = Read-Host 'Restart Explorer now to apply? [y/N]'
if ($answer -eq 'y') { Stop-Process -Name explorer -Force }
Write-Ok 'File extensions and hidden files are now visible.'
