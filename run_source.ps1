param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    & $FilePath @Arguments
    $ExitCode = $LASTEXITCODE
    if ($ExitCode -ne 0) {
        throw "Command failed with exit code ${ExitCode}: $FilePath $($Arguments -join ' ')"
    }
}

$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Repo

$Branch = (& git branch --show-current).Trim()
if ($Branch -ne "test-live-sync") {
    throw "Source runs are restricted to test-live-sync. Current branch: $Branch"
}

$Python = Join-Path $Repo ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    $PyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $PyLauncher) {
        Invoke-Checked -FilePath $PyLauncher.Source -Arguments @("-3", "-m", "venv", ".venv")
    }
    else {
        $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if ($null -eq $PythonCommand) {
            throw "Python 3 was not found."
        }
        Invoke-Checked -FilePath $PythonCommand.Source -Arguments @("-m", "venv", ".venv")
    }
}

$env:PIP_NO_CACHE_DIR = "1"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$env:RUST_COMPANION_HIDE_CONSOLE_AFTER_GUI = "1"
$env:PYTHONUNBUFFERED = "1"

Write-Host "Preparing Rust Companion+ source dependencies..." -ForegroundColor Cyan
Invoke-Checked -FilePath $Python -Arguments @(
    "-m", "pip", "install", "--no-cache-dir", "-r", "requirements.txt"
)

Write-Host "Starting Rust Companion+ from source..." -ForegroundColor Green
& $Python (Join-Path $Repo "main.py")
exit $LASTEXITCODE
