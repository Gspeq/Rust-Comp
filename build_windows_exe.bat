@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Build Rust Companion+ Single EXE
color 0E

set "PYTHON_CMD="
where py >nul 2>nul && set "PYTHON_CMD=py"
if not defined PYTHON_CMD where python >nul 2>nul && set "PYTHON_CMD=python"
if not defined PYTHON_CMD (
    echo Python 3.11 or newer was not found.
    echo Install Python from python.org and enable "Add Python to PATH".
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [BUILD 1/5] Creating local build environment...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto :failed
)

set "PY=.venv\Scripts\python.exe"
echo [BUILD 2/5] Installing application and packaging dependencies...
"%PY%" -m pip install --disable-pip-version-check --upgrade pip
"%PY%" -m pip install --disable-pip-version-check -r requirements.txt "pyinstaller>=6.11"
if errorlevel 1 goto :failed

echo [BUILD 3/5] Running compile checks and unit tests...
"%PY%" -m compileall -q launcher.py main.py rust_companion_plus
if errorlevel 1 goto :failed
"%PY%" -m unittest discover -s tests -v
if errorlevel 1 goto :failed

echo [BUILD 4/5] Bundling launcher, GUI, services, and package data into one EXE...
if exist "release\RustCompanionPlus.exe" del /q "release\RustCompanionPlus.exe"
"%PY%" -m PyInstaller --noconfirm --clean --distpath release --workpath build\pyinstaller RustCompanionPlus.spec
if errorlevel 1 goto :failed

echo [BUILD 5/5] Writing release notes and checksum...
> "release\README-FIRST-RUN.txt" echo Rust Companion+
>>"release\README-FIRST-RUN.txt" echo Developed by Taylor Marshall
>>"release\README-FIRST-RUN.txt" echo.
>>"release\README-FIRST-RUN.txt" echo Run RustCompanionPlus.exe. It waits for a live Rust server, completes and validates the exact Rust+ profile, then opens the GUI.
>>"release\README-FIRST-RUN.txt" echo Global API keys, server profiles, FCM pairing data, notes, and other saves persist in Windows AppData.
>>"release\README-FIRST-RUN.txt" echo Run: RustCompanionPlus.exe --open-data-folder
>>"release\README-FIRST-RUN.txt" echo to open the exact save directory.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$h=(Get-FileHash -Algorithm SHA256 'release\RustCompanionPlus.exe').Hash.ToLower(); Set-Content -Encoding ASCII 'release\RustCompanionPlus.exe.sha256' ($h + '  RustCompanionPlus.exe')"
if errorlevel 1 goto :failed

echo.
echo ================================================================
echo BUILD COMPLETE
echo EXE:      release\RustCompanionPlus.exe
echo CHECKSUM: release\RustCompanionPlus.exe.sha256
echo SAVES:    Run the EXE with --open-data-folder
echo ================================================================
pause
exit /b 0

:failed
echo.
echo Build failed. Review the first error above.
pause
exit /b 1
