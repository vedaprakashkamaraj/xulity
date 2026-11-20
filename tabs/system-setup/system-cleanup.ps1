. "$PSScriptRoot\..\common-script.ps1"
function Get-Size ($p) { (Get-ChildItem $p -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum }
$targets = @($env:TEMP)
if (Test-Admin) { $targets += "$env:WINDIR\Temp" }
$answer = Read-Host "Delete temp files in: $($targets -join ', ') and empty the Recycle Bin? [y/N]"
if ($answer -ne 'y') { Write-Fail 'Cancelled'; exit 1 }
$before = 0; foreach ($t in $targets) { $before += [long](Get-Size $t) }
foreach ($t in $targets) { Remove-Item "$t\*" -Recurse -Force -ErrorAction SilentlyContinue }
Clear-RecycleBin -Force -ErrorAction SilentlyContinue
Write-Ok ("Freed about {0:N1} MB." -f ($before / 1MB))
