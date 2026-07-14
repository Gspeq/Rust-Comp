param()

$ErrorActionPreference = "Stop"
$Repo = (Get-Location).Path
$Bootstrap = Join-Path $Repo "rust_companion_plus\bootstrap.py"

if (-not (Test-Path $Bootstrap)) {
    throw "Run this from the Rust-Comp repository root."
}

$Python = if (Test-Path (Join-Path $Repo ".venv\Scripts\python.exe")) {
    Join-Path $Repo ".venv\Scripts\python.exe"
}
elseif (Get-Command py -ErrorAction SilentlyContinue) {
    "py"
}
else {
    "python"
}

$Cleaner = @'
from __future__ import annotations

import sys
from pathlib import Path

repo = Path(sys.argv[1])
bootstrap = repo / "rust_companion_plus" / "bootstrap.py"
text = bootstrap.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
start = "    # RUST_COMPANION_DIAGNOSTICS_BEGIN\n"
end = "    # RUST_COMPANION_DIAGNOSTICS_END\n"

if start in text and end in text:
    before, remainder = text.split(start, 1)
    _block, after = remainder.split(end, 1)
    if after.startswith("\n"):
        after = after[1:]
    text = before + after
    bootstrap.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")

for relative in (
    "rust_companion_plus/debug_tools.py",
    "run_debug_windows.bat",
    "collect_debug_bundle.bat",
    "remove_dev_diagnostics.ps1",
    "tests/test_debug_tools.py",
):
    path = repo / relative
    if path.is_file():
        path.unlink()

print("Development diagnostics removed.")
'@

$Temp = Join-Path $env:TEMP "remove_rust_companion_debug.py"
$Cleaner | Set-Content -Path $Temp -Encoding UTF8
try {
    & $Python $Temp $Repo
    if ($LASTEXITCODE -ne 0) {
        throw "Cleanup failed."
    }
}
finally {
    Remove-Item $Temp -Force -ErrorAction SilentlyContinue
}

& $Python -m py_compile $Bootstrap
if ($LASTEXITCODE -ne 0) {
    throw "bootstrap.py did not compile after cleanup."
}

& $Python -m unittest discover -s (Join-Path $Repo "tests") -v
if ($LASTEXITCODE -ne 0) {
    throw "Tests failed after removing diagnostics."
}

Write-Host "Development diagnostics were removed cleanly." -ForegroundColor Green

# RUST_COMPANION_VERIFY_HELPER_CLEANUP
Remove-Item (Join-Path $Repo "verify_dev_build.bat") -Force -ErrorAction SilentlyContinue

# RUST_COMPANION_VISIBLE_BUNDLE_CLEANUP
Remove-Item (Join-Path $Repo "debug_bundles") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $Repo "verify_dev_build.bat") -Force -ErrorAction SilentlyContinue

# RUST_COMPANION_MULTISTAGE_DEBUG_CLEANUP
Remove-Item (Join-Path $Repo "tests\test_pairing_multistage.py") -Force -ErrorAction SilentlyContinue

# RUST_COMPANION_DEEP_PAYLOAD_DEBUG_CLEANUP
Remove-Item (Join-Path $Repo "tests\test_pairing_payload_strings_and_port_probe.py") -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $env:LOCALAPPDATA "RustCompanionPlus\Rust Companion+\debug\pairing-payload-structure.jsonl") -Force -ErrorAction SilentlyContinue
