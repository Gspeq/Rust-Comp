@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Rust Companion+ - Manual EXE Build
color 0E
echo This is the only user-facing EXE build launcher.
echo It runs only when you double-click this file.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_windows_release.ps1"
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if "%EXIT_CODE%"=="0" (
    echo Manual EXE build completed.
) else (
    echo Manual EXE build failed with code %EXIT_CODE%.
)
pause
exit /b %EXIT_CODE%
