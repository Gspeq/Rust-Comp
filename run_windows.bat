@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Rust Companion+ Launcher
color 0A

set "PYTHON_CMD="
where py >nul 2>nul && set "PYTHON_CMD=py"
if not defined PYTHON_CMD where python >nul 2>nul && set "PYTHON_CMD=python"
if not defined PYTHON_CMD (
    echo Python 3.11 or 3.12 was not found.
    echo Install Python from python.org and enable "Add Python to PATH".
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [SETUP] Creating local virtual environment...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto :failed
)

set "VENV_PY=.venv\Scripts\python.exe"
echo [SETUP] Verifying dependencies...
"%VENV_PY%" -m pip install --disable-pip-version-check --upgrade pip >nul
"%VENV_PY%" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :failed

"%VENV_PY%" launcher.py
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo.
    echo Rust Companion+ exited with code %EXIT_CODE%.
    pause
)
exit /b %EXIT_CODE%

:failed
echo.
echo Setup failed. Review the error above.
pause
exit /b 1
