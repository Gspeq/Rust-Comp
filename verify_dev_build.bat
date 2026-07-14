@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Rust Companion+ Development Verification

set "PYTHON_CMD="
if exist ".venv\Scripts\python.exe" set "PYTHON_CMD=.venv\Scripts\python.exe"
if not defined PYTHON_CMD where py >nul 2>nul && set "PYTHON_CMD=py"
if not defined PYTHON_CMD where python >nul 2>nul && set "PYTHON_CMD=python"
if not defined PYTHON_CMD (
    echo Python was not found.
    pause
    exit /b 1
)

echo [1/3] Compiling project...
"%PYTHON_CMD%" -m compileall -q rust_companion_plus tests
if errorlevel 1 goto :failed

echo [2/3] Running all tests...
"%PYTHON_CMD%" -m unittest discover -s tests -v
if errorlevel 1 goto :failed

echo [3/3] Checking Git patch...
git diff --check
if errorlevel 1 goto :failed

echo.
echo ALL DEVELOPMENT CHECKS PASSED.
git status --short
pause
exit /b 0

:failed
echo.
echo DEVELOPMENT VERIFICATION FAILED.
pause
exit /b 1
