
@echo off
setlocal EnableExtensions
cd /d "%~dp0"
start "Rust Companion+ Source" powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_source.ps1"
exit /b 0
