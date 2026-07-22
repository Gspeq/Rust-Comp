@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Rust Companion+ - Run From Source
color 0A
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_source.ps1"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo.
    echo Source launch failed with code %EXIT_CODE%.
    pause
)
exit /b %EXIT_CODE%
