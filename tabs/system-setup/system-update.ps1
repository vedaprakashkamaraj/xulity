. "$PSScriptRoot\..\common-script.ps1"
$pm = Get-Packager
Write-Info "Updating all packages with $pm ..."
switch ($pm) {
    'winget' { winget upgrade --all --accept-package-agreements --accept-source-agreements }
    'choco'  { choco upgrade all -y }
    'scoop'  { scoop update '*' }
}
Write-Ok 'Package update finished.'
