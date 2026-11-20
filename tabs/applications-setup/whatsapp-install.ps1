# WhatsApp from the Microsoft Store (winget's community repo no longer carries it).
. "$PSScriptRoot\..\common-script.ps1"
if (-not (Test-CommandExists winget)) {
    Write-Fail 'winget is needed. Install "App Installer" from the Microsoft Store, then try again.'
    exit 1
}
Write-Info 'Installing WhatsApp (Microsoft Store id 9NKSQGP7F2NH)...'
winget install -e --id 9NKSQGP7F2NH --source msstore --accept-package-agreements --accept-source-agreements
if ($LASTEXITCODE -ne 0) {
    Write-Warn 'winget could not install it. Opening the Store page instead; press Install there.'
    Start-Process 'ms-windows-store://pdp/?productid=9NKSQGP7F2NH'
    exit 1
}
Write-Ok 'Done.'
