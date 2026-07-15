@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Rust Companion+ Windows Release Builder
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_windows_release.ps1"
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" (
    echo Release build failed with code %EXIT_CODE%.
) else (
    echo Release builder finished.
)
pause
exit /b %EXIT_CODE%
