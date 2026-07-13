@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Build Rust Companion+ EXE

set "PYTHON_CMD="
where py >nul 2>nul && set "PYTHON_CMD=py"
if not defined PYTHON_CMD where python >nul 2>nul && set "PYTHON_CMD=python"
if not defined PYTHON_CMD (
    echo Python 3.11 or 3.12 was not found.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto :failed
)

set "PY=.venv\Scripts\python.exe"
"%PY%" -m pip install --disable-pip-version-check --upgrade pip
"%PY%" -m pip install --disable-pip-version-check -r requirements.txt pyinstaller
if errorlevel 1 goto :failed

"%PY%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --name "RustCompanionPlus" ^
  --console ^
  --collect-all customtkinter ^
  --collect-all rustplus ^
  --hidden-import rust_companion_plus.app ^
  --add-data "rust_companion_plus\data;rust_companion_plus\data" ^
  launcher.py
if errorlevel 1 goto :failed

echo.
echo Build complete: dist\RustCompanionPlus\RustCompanionPlus.exe
pause
exit /b 0

:failed
echo.
echo EXE build failed. Review the error above.
pause
exit /b 1
