param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Repo = (Get-Location).Path
if (-not (Test-Path (Join-Path $Repo ".git"))) {
    throw "Run this from the Rust-Comp repository."
}

$Files = @(
    "run_debug_windows.bat",
    "collect_debug_bundle.bat",
    "verify_dev_build.bat",
    "rust_companion_plus\debug_tools.py",
    "tests\test_pairing_signed_token_app_data.py",
    "tests\test_pairing_launcher_baseline.py"
)

foreach ($Relative in $Files) {
    Remove-Item (Join-Path $Repo $Relative) -Force -ErrorAction SilentlyContinue
}

Remove-Item (Join-Path $Repo "debug_bundles") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (
    Join-Path $env:LOCALAPPDATA
    "RustCompanionPlus\Rust Companion+\debug"
) -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "Temporary development diagnostics removed." -ForegroundColor Green
Write-Host "Core Rust+ pairing fixes were intentionally retained."
