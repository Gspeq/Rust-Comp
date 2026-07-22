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
    throw "Source testing is restricted to test-live-sync. Current branch: $Branch"
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

Invoke-Checked -FilePath $Python -Arguments @(
    "-m", "pip", "install", "--no-cache-dir", "-r", "requirements.txt"
)
Invoke-Checked -FilePath $Python -Arguments @(
    "-m", "compileall", "-q", "launcher.py", "main.py", "rust_companion_plus"
)

# unittest discover
Invoke-Checked -FilePath $Python -Arguments @(
    "-m", "unittest", "discover", "-s", "tests", "-v"
)

# git diff --check
Invoke-Checked -FilePath "git" -Arguments @("diff", "--check")

Write-Host "All source checks passed. No EXE was built." -ForegroundColor Green
exit 0
