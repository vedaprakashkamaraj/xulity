. "$PSScriptRoot\..\common-script.ps1"
Assert-Admin
if (-not (Test-CommandExists Start-MpScan)) { Write-Fail 'Microsoft Defender cmdlets not available.'; exit 1 }
Write-Info 'Updating signatures...'
Update-MpSignature
Write-Info 'Running quick scan...'
Start-MpScan -ScanType QuickScan
$t = Get-MpThreatDetection
if ($t) { $t | Format-Table InitialDetectionTime, ProcessName, Resources } else { Write-Ok 'No threats detected.' }
