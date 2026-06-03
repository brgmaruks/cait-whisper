@echo off
setlocal
cd /d "%~dp0"
title Cait Whisper

:: ──────────────────────────────────────────────────────────────────────────
::  Cait Whisper - ONE launcher for first run AND every run after.
::
::    First run  : no environment yet  -> set everything up (one time), then
::                 launch.
::    Every run  : environment exists   -> just launch.
::
::  Double-click this. That's the whole story. (This is the source/developer
::  launcher. The prebuilt download is a single Cait Whisper.exe that needs
::  no setup at all.)
:: ──────────────────────────────────────────────────────────────────────────

:: First-run setup: only happens if the virtual environment isn't there yet.
if not exist "venv\Scripts\pythonw.exe" (
    echo.
    echo   Welcome to Cait Whisper.
    echo   First-time setup - this happens once and takes a few minutes.
    echo.
    set "CW_CHAINED=1"
    call "%~dp0setup.bat"
    set "CW_CHAINED="
    if not exist "venv\Scripts\pythonw.exe" (
        echo.
        echo   [!] Setup didn't finish. See the messages above, then try again.
        echo.
        pause
        exit /b 1
    )
)

:: Every run: start.bat elevates to admin (needed for the global hotkey) and
:: launches the app with no console window.
call "%~dp0start.bat"
