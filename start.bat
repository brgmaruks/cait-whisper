@echo off
setlocal
cd /d "%~dp0"
title cait-whisper

:: ── Re-launch as Administrator if not already elevated ───────────────────────
:: (Required for the Ctrl+Win global hotkey to work on Windows)
net session >nul 2>&1
if errorlevel 1 (
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
    exit /b
)

:: ── Check setup was run ───────────────────────────────────────────────────────
if not exist venv\Scripts\activate.bat (
    echo.
    echo  [!] Virtual environment not found.
    echo      Please run setup.bat first.
    echo.
    pause
    exit /b 1
)

:: ── Detect stale venv (folder was moved) ─────────────────────────────────────
:: venv\Scripts\activate.bat has: set "VIRTUAL_ENV=<original_path>\venv"
:: If that path doesn't match our current location, the venv is broken.
set "EXPECTED_VENV=%~dp0venv"
:: Strip trailing backslash for clean comparison
if "%EXPECTED_VENV:~-1%"=="\" set "EXPECTED_VENV=%EXPECTED_VENV:~0,-1%"

for /f "tokens=1,* delims==" %%A in ('findstr /C:"VIRTUAL_ENV=" venv\Scripts\activate.bat') do (
    set "FOUND_VENV=%%B"
)
:: Strip surrounding quotes from the found path
set "FOUND_VENV=%FOUND_VENV:"=%"

if /i not "%FOUND_VENV%"=="%EXPECTED_VENV%" (
    echo.
    echo  [!] Virtual environment was created for a different folder.
    echo      Old: %FOUND_VENV%
    echo      Now: %EXPECTED_VENV%
    echo.
    echo  Recreating venv... this takes 1-2 minutes.
    echo.
    rmdir /s /q venv
    call "%~dp0setup.bat"
    if not exist venv\Scripts\pythonw.exe (
        echo  [!] Setup failed. Check the output above.
        pause
        exit /b 1
    )
)

:: ── Activate venv ─────────────────────────────────────────────────────────────
call venv\Scripts\activate.bat

:: ── Launch ───────────────────────────────────────────────────────────────────
:: Ollama is started on-demand when you enable "LLM Cleanup" from the tray menu.
echo  Starting cait-whisper...
echo  (First launch loads the ASR model — Moonshine is fast, Whisper takes longer)
echo.
echo  Hotkeys:
echo    Ctrl + Win  (hold)      hold-to-talk
echo    Ctrl + Win + Space      hands-free toggle
echo    Alt  + Shift + Z        re-paste last transcription
echo.

:: Use the explicit venv pythonw.exe path — avoids PATH inheritance issues
:: with elevated/detached processes. No console window appears.
if not exist "%~dp0venv\Scripts\pythonw.exe" (
    echo  [!] venv\Scripts\pythonw.exe not found.
    echo      Please run setup.bat first.
    pause
    exit /b 1
)

start "" "%~dp0venv\Scripts\pythonw.exe" "%~dp0client.py"

:: Any startup errors appear as a dialog box and are written to cait-whisper.log
echo  Running. Check cait-whisper.log if anything goes wrong.
timeout /t 2 /nobreak >nul
