# xutil installer for Windows (PowerShell).
#   .\install.ps1            install to %LOCALAPPDATA%\xutil and add Start Menu + Desktop shortcuts
#   .\install.ps1 -Run       install, then open the window
#   .\install.ps1 -Uninstall remove everything this script added
param([switch]$Run, [switch]$Uninstall)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$app  = Join-Path $env:LOCALAPPDATA 'xutil'
$menu = Join-Path ([Environment]::GetFolderPath('Programs')) 'xutil.lnk'
$desk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'xutil.lnk'

if ($Uninstall) {
    Remove-Item $app, $menu, $desk -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host 'xutil removed.' -ForegroundColor Green; exit 0
}

function Find-Python {
    foreach ($c in @(@('py', '-3'), @('python'), @('python3'))) {
        if (Get-Command $c[0] -ErrorAction SilentlyContinue) {
            $extra = @($c | Select-Object -Skip 1)
            & $c[0] @extra -c "import sys, tkinter; sys.exit(sys.version_info < (3, 11))" 2>$null
            if ($LASTEXITCODE -eq 0) { return ,$c }
        }
    }
    return $null
}
$py = Find-Python
if (-not $py) {
    Write-Host 'Installing Python 3.12 (with tkinter) via winget...' -ForegroundColor Cyan
    winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
    $py = Find-Python
    if (-not $py) { Write-Host 'Python 3.11+ with tkinter not found. Reopen PowerShell and run this again.' -ForegroundColor Red; exit 1 }
}
# pythonw.exe = no console window behind the GUI
$exe  = (& $py[0] @($py | Select-Object -Skip 1) -c "import sys; print(sys.executable)").Trim()
$pyw  = Join-Path (Split-Path $exe) 'pythonw.exe'
if (-not (Test-Path $pyw)) { $pyw = $exe }

Write-Host "Installing to $app" -ForegroundColor Cyan
Remove-Item $app -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $app | Out-Null
Copy-Item (Join-Path $here 'xutil.py'), (Join-Path $here 'xutil_icons.py') $app
Copy-Item (Join-Path $here 'tabs'), (Join-Path $here 'assets') $app -Recurse
Get-ChildItem $app -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force

# command-line launcher: `xutil` (add %LOCALAPPDATA%\xutil to PATH to use it anywhere)
Set-Content (Join-Path $app 'xutil.cmd') "@echo off`r`n`"$exe`" `"$app\xutil.py`" %*"

$sh = New-Object -ComObject WScript.Shell
foreach ($lnk in @($menu, $desk)) {
    $s = $sh.CreateShortcut($lnk)
    $s.TargetPath = $pyw
    $s.Arguments = "`"$app\xutil.py`" --gui"
    $s.WorkingDirectory = $app
    $s.IconLocation = (Join-Path $app 'assets\xutil.ico')
    $s.Description = 'Install apps and set up your system'
    $s.Save()
}
& $exe (Join-Path $app 'xutil.py') --check
Write-Host 'Installed. Open "xutil" from the Start Menu. Right-click it and choose "Run as administrator" for admin tasks.' -ForegroundColor Green
if ($Run) { Start-Process $pyw -ArgumentList "`"$app\xutil.py`"", '--gui' }
