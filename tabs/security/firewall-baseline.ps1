. "$PSScriptRoot\..\common-script.ps1"
Assert-Admin
Set-NetFirewallProfile -Profile Domain,Private,Public -Enabled True -DefaultInboundAction Block -DefaultOutboundAction Allow
Get-NetFirewallProfile | Format-Table Name, Enabled, DefaultInboundAction, DefaultOutboundAction
Write-Ok 'Windows Firewall enabled on all profiles; inbound blocked by default.'
