. "$PSScriptRoot\..\common-script.ps1"
Assert-Admin
Enable-ComputerRestore -Drive "$env:SystemDrive\"
Checkpoint-Computer -Description ("xutil " + (Get-Date -Format 'yyyy-MM-dd HH:mm')) -RestorePointType MODIFY_SETTINGS
Write-Ok 'Restore point created. (Windows allows one automatic point per 24 hours by default.)'
