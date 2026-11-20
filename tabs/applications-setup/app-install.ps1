# Generic installer: app-install.ps1 <winget-id> [choco-name] [scoop-name]
param([Parameter(Mandatory)][string]$Winget, [string]$Choco, [string]$Scoop)
. "$PSScriptRoot\..\common-script.ps1"
Write-Info "Architecture: $(Get-Arch)"
Install-Package -Winget $Winget -Choco $Choco -Scoop $Scoop
Write-Ok 'Done.'
