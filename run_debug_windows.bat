@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Rust Companion+ Development Diagnostics

set "PYTHON_CMD="
if exist ".venv\Scripts\python.exe" set "PYTHON_CMD=.venv\Scripts\python.exe"
if not defined PYTHON_CMD where py >nul 2>nul && set "PYTHON_CMD=py"
if not defined PYTHON_CMD where python >nul 2>nul && set "PYTHON_CMD=python"
if not defined PYTHON_CMD (
    echo Python was not found.
    pause
    exit /b 1
)

set "RUST_COMPANION_DEBUG_CONSOLE=1"
"%PYTHON_CMD%" -c "from rust_companion_plus import bootstrap, debug_tools; debug_tools.install_debug_runtime(bootstrap); raise SystemExit(bootstrap.main())"
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" echo Launcher exited with code %EXIT_CODE%.
pause
exit /b %EXIT_CODE%
