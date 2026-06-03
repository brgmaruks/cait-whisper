@echo off
cd /d "%~dp0"
title Create Cait Whisper launcher
echo.
echo  Creating a branded "Cait Whisper" shortcut on your Desktop...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0make_launcher.ps1"
echo.
pause
