
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Repo
$Python = Join-Path $Repo ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "Missing project Python environment." -ForegroundColor Red
    exit 1
}

& $Python -m unittest discover -s (Join-Path $Repo "tests") -v
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& git diff --check
exit $LASTEXITCODE
