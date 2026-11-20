# One-line launcher for Windows PowerShell:
#   irm https://raw.githubusercontent.com/YOUR_USER/xutil/main/get.ps1 | iex
$Repo   = if ($env:XUTIL_REPO)   { $env:XUTIL_REPO }   else { 'YOUR_USER/xutil' }
$Branch = if ($env:XUTIL_BRANCH) { $env:XUTIL_BRANCH } else { 'main' }
$tmp = Join-Path $env:TEMP ("xutil_" + [guid]::NewGuid().ToString('N'))
try {
    New-Item -ItemType Directory -Path $tmp | Out-Null
    $zip = Join-Path $tmp 'x.zip'
    Invoke-WebRequest "https://github.com/$Repo/archive/refs/heads/$Branch.zip" -OutFile $zip
    Expand-Archive $zip -DestinationPath $tmp
    $root = Get-ChildItem $tmp -Directory | Select-Object -First 1
    & "$($root.FullName)\run.ps1"
} finally {
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
