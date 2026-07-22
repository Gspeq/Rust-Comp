@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Rust Companion+ - Test Then Run From Source
color 0A

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\windows\run_source.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Rust Companion+ did not start because synchronization, setup, or tests failed.
    pause
)
exit /b %EXIT_CODE%
