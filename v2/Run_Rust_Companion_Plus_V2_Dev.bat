@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Rust Companion+ 2.0 Development
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\run_dev.ps1"
if errorlevel 1 pause
