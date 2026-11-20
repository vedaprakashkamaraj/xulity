# Office / Word 2013 installer: runs YOUR OWN Office 2013 setup (setup.exe, or an .iso from your disc or Microsoft account).
# xutil does not download, crack or activate Office; you enter your own product key in Microsoft's installer.
param([string]$Path)
. "$PSScriptRoot\..\common-script.ps1"
Write-Warn 'Office 2013 is no longer sold or supported by Microsoft (support ended April 2023).'
Write-Info 'This uses your own installer and product key. For a current Word use the "Microsoft Word" entry (Microsoft 365).'
if (-not $Path) {
    try {
        Add-Type -AssemblyName System.Windows.Forms
        $dlg = New-Object System.Windows.Forms.OpenFileDialog
        $dlg.Title = 'Select your Office 2013 setup.exe or .iso'
        $dlg.Filter = 'Office setup (setup.exe;*.iso)|setup.exe;*.iso|All files (*.*)|*.*'
        if ($dlg.ShowDialog() -ne 'OK') { Write-Fail 'Cancelled.'; exit 1 }
        $Path = $dlg.FileName
    } catch {
        $Path = (Read-Host 'Path to your Office 2013 setup.exe or .iso').Trim('"')
    }
}
if (-not (Test-Path $Path)) { Write-Fail "Not found: $Path"; exit 1 }
$iso = $null
if ($Path -like '*.iso') {
    Write-Info "Mounting $Path ..."
    $iso = $Path
    $img = Mount-DiskImage -ImagePath $iso -PassThru
    $letter = ($img | Get-Volume).DriveLetter
    $Path = "${letter}:\setup.exe"
    if (-not (Test-Path $Path)) {
        Dismount-DiskImage -ImagePath $iso | Out-Null
        Write-Fail 'No setup.exe found at the top of that ISO.'
        exit 1
    }
}
Write-Info "Starting $Path . Follow the installer and enter your product key when asked."
$p = Start-Process -FilePath $Path -Wait -PassThru
if ($iso) { Dismount-DiskImage -ImagePath $iso | Out-Null }
if ($p.ExitCode -ne 0) { Write-Fail "Setup ended with exit code $($p.ExitCode)"; exit $p.ExitCode }
Write-Ok 'Office setup finished.'
