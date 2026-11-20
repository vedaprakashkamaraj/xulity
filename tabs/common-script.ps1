# Shared helpers for Windows scripts (counterpart of common-script.sh).
$ErrorActionPreference = 'Stop'

function Write-Info  ($m) { Write-Host $m -ForegroundColor Cyan }
function Write-Warn  ($m) { Write-Host $m -ForegroundColor Yellow }
function Write-Fail  ($m) { Write-Host $m -ForegroundColor Red }
function Write-Ok    ($m) { Write-Host $m -ForegroundColor Green }

function Test-CommandExists ([string]$Name) { [bool](Get-Command $Name -ErrorAction SilentlyContinue) }

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal $id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# Fail fast (spec: "stop on unsupported or ambiguous conditions") instead of half-running.
function Assert-Admin {
    if (-not (Test-Admin)) {
        Write-Fail 'This task needs Administrator rights. Re-open your terminal as Administrator and run xutil again.'
        exit 1
    }
}

function Get-Packager {
    foreach ($p in 'winget', 'choco', 'scoop') { if (Test-CommandExists $p) { return $p } }
    Write-Fail 'No supported package manager found (winget, choco or scoop).'
    exit 1
}

function Get-Arch {
    switch ($env:PROCESSOR_ARCHITECTURE) {
        'AMD64' { 'x86_64' } 'ARM64' { 'aarch64' }
        default { Write-Fail "Unsupported architecture: $env:PROCESSOR_ARCHITECTURE"; exit 1 }
    }
}

# Install-Package -Winget <id> [-Choco <name>] [-Scoop <name>]
function Install-Package {
    param([string]$Winget, [string]$Choco, [string]$Scoop)
    $pm = Get-Packager
    Write-Info "Using $pm as package manager"
    switch ($pm) {
        'winget' { winget install -e --id $Winget --accept-package-agreements --accept-source-agreements }
        'choco'  { if ($Choco) { choco install -y $Choco } else { Write-Fail 'No Chocolatey name for this app.'; exit 1 } }
        'scoop'  { if ($Scoop) { scoop install $Scoop }   else { Write-Fail 'No Scoop name for this app.'; exit 1 } }
    }
    if ($LASTEXITCODE -ne 0) { Write-Fail "Install failed (exit $LASTEXITCODE)"; exit $LASTEXITCODE }
}
