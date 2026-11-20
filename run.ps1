# Launcher for Windows: finds Python 3.11+ (py launcher or python) and starts xutil.
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
foreach ($py in @('py', 'python', 'python3')) {
    if (Get-Command $py -ErrorAction SilentlyContinue) {
        & $py -c "import sys; sys.exit(sys.version_info < (3, 11))"
        if ($LASTEXITCODE -eq 0) { & $py "$dir\xutil.py" @args; exit $LASTEXITCODE }
    }
}
Write-Host 'xutil needs Python 3.11+. Install it with: winget install Python.Python.3.12' -ForegroundColor Red
exit 1
