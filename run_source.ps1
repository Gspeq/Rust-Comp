
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "ERROR: $Message" -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Repo

$Branch = (& git branch --show-current).Trim()
if ($Branch -ne "test-live-sync") {
    Fail "Source testing is restricted to test-live-sync. Current branch: $Branch"
}

$Python = Join-Path $Repo ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Fail "Missing project Python environment: $Python"
}

$env:RUST_COMPANION_HIDE_CONSOLE_AFTER_GUI = "1"
$env:PYTHONUNBUFFERED = "1"

Write-Host ""
Write-Host "Rust Companion+ source test" -ForegroundColor Cyan
Write-Host "No EXE or installer will be built."
Write-Host ""

& $Python (Join-Path $Repo "main.py")
$ExitCode = $LASTEXITCODE

if ($ExitCode -ne 0) {
    Write-Host ""
    Write-Host "Rust Companion+ exited with code $ExitCode." -ForegroundColor Red
    Read-Host "Press Enter to close"
}

exit $ExitCode
