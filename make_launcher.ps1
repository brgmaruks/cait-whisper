# make_launcher.ps1
# -----------------
# Creates a branded "Cait Whisper" shortcut on the Desktop:
#   - the Phi-in-circle icon (assets\cait.ico)
#   - launches the app with pythonw (NO console window - just the splash, then
#     the coin)
#   - flagged "Run as administrator" so the global Ctrl+Win hotkey works
#
# Run it once via "Create Launcher.bat". After that, double-click the
# "Cait Whisper" icon on your Desktop to launch - that's the go-forward
# launcher for the source install.

$ErrorActionPreference = 'Stop'
$repo    = $PSScriptRoot
$ico     = Join-Path $repo 'assets\cait.ico'
$pythonw = Join-Path $repo 'venv\Scripts\pythonw.exe'

if (-not (Test-Path $pythonw)) {
    Write-Host "venv not found. Double-click 'Cait Whisper.bat' once to set up first." -ForegroundColor Yellow
    exit 1
}

# Make sure the brand icon exists (regenerate if missing).
if (-not (Test-Path $ico)) {
    & (Join-Path $repo 'venv\Scripts\python.exe') -c "import theme; theme.ensure_brand_ico('assets/cait.ico')"
}

$desktop = [Environment]::GetFolderPath('Desktop')
$lnk     = Join-Path $desktop 'Cait Whisper.lnk'

$ws = New-Object -ComObject WScript.Shell
$s  = $ws.CreateShortcut($lnk)
$s.TargetPath       = $pythonw
$s.Arguments        = 'client.py'
$s.WorkingDirectory = $repo
$s.IconLocation     = $ico
$s.Description       = 'Cait Whisper - local voice to text'
$s.Save()

# Set the "Run as administrator" flag (bit 0x20 of the LinkFlags byte at
# offset 0x15). WScript.Shell can't set this, so we patch the .lnk bytes.
$bytes = [IO.File]::ReadAllBytes($lnk)
$bytes[0x15] = $bytes[0x15] -bor 0x20
[IO.File]::WriteAllBytes($lnk, $bytes)

Write-Host ""
Write-Host "Created branded launcher: $lnk" -ForegroundColor Green
Write-Host "Double-click 'Cait Whisper' on your Desktop to run (no console, branded icon)."
Write-Host ""
