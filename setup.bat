@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title cait-whisper Setup

echo.
echo  ================================================
echo   cait-whisper  ^|  Setup
echo  ================================================
echo.

:: ── Check Python ─────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [!] Python was not found on your PATH.
    echo.
    where winget >nul 2>&1
    if not errorlevel 1 (
        set /p INSTALL_PY="  Install Python 3.13 automatically via winget? [Y/n]: "
        if /i not "!INSTALL_PY!"=="n" (
            winget install -e --id Python.Python.3.13 --accept-package-agreements --accept-source-agreements
            echo.
            echo  Python installed. Please close this window and re-run setup.bat
            echo  so the new PATH is picked up.
            echo.
            pause
            exit /b 0
        )
    )
    echo  Please install Python 3.10 or later from:
    echo  https://www.python.org/downloads/
    echo.
    echo  Make sure to check "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo  Python found: %%v
echo.

:: ── Create virtual environment ───────────────────────────────────────────────
:: If venv exists, check it wasn't created for a different folder (moved install)
if exist venv\Scripts\activate.bat (
    set "EXPECTED_VENV=%~dp0venv"
    if "!EXPECTED_VENV:~-1!"=="\" set "EXPECTED_VENV=!EXPECTED_VENV:~0,-1!"
    for /f "tokens=1,* delims==" %%A in ('findstr /C:"VIRTUAL_ENV=" venv\Scripts\activate.bat') do (
        set "FOUND_VENV=%%B"
    )
    set "FOUND_VENV=!FOUND_VENV:"=!"
    if /i not "!FOUND_VENV!"=="!EXPECTED_VENV!" (
        echo  [!] Stale venv detected (folder was moved^).
        echo      Old: !FOUND_VENV!
        echo      Now: !EXPECTED_VENV!
        echo.
        echo      Removing stale venv...
        rmdir /s /q venv
    )
)

if not exist venv (
    echo  [1/4] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo  [!] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo        Done.
) else (
    echo  [1/4] Virtual environment already exists, skipping.
)
echo.

call venv\Scripts\activate.bat

:: ── Core packages via requirements.txt ────────────────────────────────────────
echo  [2/4] Installing core packages from requirements.txt...
echo         ASR engines, audio, keyboard, clipboard, UI Automation, OCR...
echo.

pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo  [!] Some packages failed. Check the output above.
    echo      You can comment out optional lines in requirements.txt and retry.
    pause
    exit /b 1
)
echo.
echo        Core packages installed.
echo.

:: ── Optional: Parakeet / NeMo — blocked on Python 3.12+ ──────────────────────
echo  [3/4] Parakeet (NVIDIA NeMo) - checking Python compatibility...
echo.

:: NeMo requires Python 3.10 or 3.11; torch CPU wheels for those versions
:: max out at 2.4.x.  Python 3.12+ only has torch 2.6+, which NeMo rejects.
:: Detect minor version and skip automatically if incompatible.
for /f "tokens=2" %%V in ('python -c "import sys; print(sys.version_info.minor)"') do set PY_MINOR=%%V

if defined PY_MINOR if %PY_MINOR% GEQ 12 (
    echo   [!] Parakeet unavailable - NeMo does not support Python 3.1%PY_MINOR%.
    echo.
    echo       NeMo needs Python 3.10 or 3.11.  Your best alternative is:
    echo         distil-whisper/distil-large-v3  (Switch Model menu in the app^)
    echo       It gives near-identical accuracy with no extra install.
    echo.
    echo       Parakeet will be greyed out in the app menu.
    echo.
    goto :nemo_done
)

echo         30x faster than real-time on CPU, beats Whisper Large accuracy.
echo         Needs ~250 MB of PyTorch + ~1-2 GB NeMo.  Model downloads on first use.
echo.
set /p INSTALL_NEMO="  Install Parakeet support? [y/N]: "
if /i not "%INSTALL_NEMO%"=="y" goto :skip_nemo

echo.
echo   Installing PyTorch CPU (2.4.x for NeMo compatibility)...
pip install "torch==2.4.1" --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 (
    echo.
    echo   [!] PyTorch install failed - see error above.
    pause
    goto :skip_nemo
)

echo.
echo   Installing NeMo ASR toolkit (this may take several minutes)...
pip install "nemo_toolkit[asr]"
if errorlevel 1 (
    echo.
    echo   [!] NeMo install failed - see error above.
    echo       Retry: venv\Scripts\pip install "nemo_toolkit[asr]"
    pause
    goto :skip_nemo
)

echo.
echo   Parakeet support installed successfully.
goto :nemo_done

:skip_nemo
echo   Skipping Parakeet.

:nemo_done
echo.

:: ── Optional: Ollama (LLM transcript cleanup + voice commands) ────────────────
echo  [4/4] Optional: Ollama (required for selection-based voice commands
echo         and optional LLM cleanup)
echo.
echo         Used by COMMAND mode for "shorten this", "summarize this", etc.
echo         Also used by the optional LLM Cleanup toggle.
echo         Requires ~2 GB for the default language model (downloads once).
echo.
echo         Skip this if you only want plain dictation.
echo.
set /p INSTALL_OLLAMA="  Set up Ollama? [y/N]: "
if /i not "%INSTALL_OLLAMA%"=="y" goto :skip_ollama

ollama --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo   Ollama is not installed.
    where winget >nul 2>&1
    if not errorlevel 1 (
        set /p DO_WINGET="   Install Ollama via winget now? [Y/n]: "
        if /i not "!DO_WINGET!"=="n" (
            winget install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements
            echo.
            echo   Ollama installed. Checking service...
            timeout /t 3 >nul
        ) else (
            start https://ollama.com/download/windows
            echo   Install Ollama manually, then re-run setup.bat to pull the model.
            pause
            goto :skip_ollama
        )
    ) else (
        start https://ollama.com/download/windows
        echo   Install Ollama manually, then re-run setup.bat to pull the model.
        pause
        goto :skip_ollama
    )
)

for /f "tokens=*" %%v in ('ollama --version 2^>^&1') do echo   Ollama: %%v
echo   Pulling llama3.2:3b model...
echo.
ollama pull llama3.2:3b
if errorlevel 1 (
    echo.
    echo   [!] Could not pull model. Make sure Ollama is running and try again.
    goto :skip_ollama
)
echo.
echo   Ollama model ready.
goto :ollama_done

:skip_ollama
echo   Skipping Ollama.

:ollama_done
echo.

:: ── Create config.json if not present ────────────────────────────────────────
if not exist config.json (
    echo  Creating config.json from config.example.json...
    copy /y config.example.json config.json >nul
    echo   config.json created.  Edit it to change engines, models, or appearance.
) else (
    echo  config.json already exists - not overwritten.
)
echo.

:: ── Done ──────────────────────────────────────────────────────────────────────
echo  ================================================
echo   Setup complete!
echo.
echo   Run start.bat to begin dictating.
echo.
echo   Hotkeys:
echo     Ctrl + Win  (hold)       hold-to-talk
echo     Ctrl + Win + Space       hands-free toggle
echo     Shift + Alt + R          retroactive capture (last ~15 s)
echo     Shift + Alt + C          one-shot COMMAND mode
echo     Shift + Alt + Z          re-paste last transcription
echo.
echo   See docs/ for the full manual.
echo  ================================================
echo.
pause
