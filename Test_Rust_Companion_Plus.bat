
@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Rust Companion+ Source Tests
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0test_source.ps1"
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if "%EXIT_CODE%"=="0" (
    echo Source tests passed. No EXE was built.
) else (
    echo Source tests failed with code %EXIT_CODE%.
)
pause
exit /b %EXIT_CODE%
