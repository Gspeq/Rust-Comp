@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Rust Companion+ - Manual EXE Build
color 0E

echo This is the only EXE build launcher.
echo Source runs never build an EXE.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\windows\build_windows_release.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo Manual EXE build completed.
) else (
    echo Manual EXE build failed with code %EXIT_CODE%.
)
pause
exit /b %EXIT_CODE%
