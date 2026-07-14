@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Rust Companion+ Single Review File

set "PYTHON_CMD="
if exist ".venv\Scripts\python.exe" set "PYTHON_CMD=.venv\Scripts\python.exe"
if not defined PYTHON_CMD where py >nul 2>nul && set "PYTHON_CMD=py"
if not defined PYTHON_CMD where python >nul 2>nul && set "PYTHON_CMD=python"
if not defined PYTHON_CMD (
    echo Python was not found.
    pause
    exit /b 1
)

set "REPORT_DIR=%CD%\debug_bundles"
"%PYTHON_CMD%" -m rust_companion_plus.debug_tools --review --output "%REPORT_DIR%" --open-folder
if errorlevel 1 (
    echo Review report creation failed.
    pause
    exit /b 1
)

echo.
echo Upload only the newest rust-companion-review-*.txt file from:
echo   %REPORT_DIR%
echo.
if exist "%REPORT_DIR%\latest-review-report.txt" (
    echo Exact report:
    type "%REPORT_DIR%\latest-review-report.txt"
    echo.
)
pause
