. "$PSScriptRoot\..\common-script.ps1"
Assert-Admin
$cap = Get-WindowsCapability -Online -Name 'OpenSSH.Server*'
if ($cap.State -ne 'Installed') { Add-WindowsCapability -Online -Name $cap.Name | Out-Null }
Set-Service sshd -StartupType Automatic
Start-Service sshd
Get-Service sshd | Format-Table Name, Status, StartType
Write-Ok 'OpenSSH server installed and running (port 22).'
