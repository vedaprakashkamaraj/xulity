. "$PSScriptRoot\..\common-script.ps1"
Assert-Admin
Write-Info 'Step 1/2: DISM component store repair'
DISM /Online /Cleanup-Image /RestoreHealth
if ($LASTEXITCODE -ne 0) { Write-Fail "DISM failed ($LASTEXITCODE)"; exit $LASTEXITCODE }
Write-Info 'Step 2/2: System File Checker'
sfc /scannow
exit $LASTEXITCODE
