. "$PSScriptRoot\..\common-script.ps1"
Assert-Admin
if (-not (Test-CommandExists wsl)) { Write-Fail 'wsl.exe not found. Requires Windows 10 2004+ or Windows 11.'; exit 1 }
wsl --install
Write-Warn 'A reboot is usually required to finish enabling WSL.'
