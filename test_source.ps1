param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "TESTS FAILED: $Message" -ForegroundColor Red
    exit 1
}

$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Repo

if (-not (Test-Path (Join-Path $Repo ".git"))) {
    Fail "This test runner must stay in the Rust-Comp repository root."
}

$Branch = (& git branch --show-current).Trim()
if ($Branch -ne "test-live-sync") {
    Fail "Tests are restricted to test-live-sync. Current branch: $Branch"
}

$Python = Join-Path $Repo ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Fail "Missing project environment: $Python"
}

Write-Host ""
Write-Host "Rust Companion+ source test suite" -ForegroundColor Cyan
Write-Host "No EXE or installer will be created."
Write-Host ""

& $Python -m unittest discover -s (Join-Path $Repo "tests") -v
if ($LASTEXITCODE -ne 0) {
    Fail "The Python test suite failed."
}

& git diff --check
if ($LASTEXITCODE -ne 0) {
    Fail "git diff --check found a formatting problem."
}

Write-Host ""
Write-Host "ALL SOURCE TESTS PASSED" -ForegroundColor Green
Write-Host "The release builder was not run."
