@echo off
setlocal
cd /d "%~dp0"
title cait-whisper  ^|  Build the downloadable app

echo.
echo  ================================================
echo   cait-whisper  ^|  Building the click-to-run app
echo  ================================================
echo.

:: ── Need the venv (created by setup.bat) ──────────────────────────────────────
if not exist venv\Scripts\activate.bat (
    echo  [!] Virtual environment not found. Run setup.bat first.
    pause
    exit /b 1
)
call venv\Scripts\activate.bat

:: ── Ensure PyInstaller is installed in the venv ───────────────────────────────
echo  Ensuring PyInstaller is installed...
python -m pip install --quiet --upgrade pyinstaller
if errorlevel 1 (
    echo  [!] Could not install PyInstaller.
    pause
    exit /b 1
)

:: ── Generate the brand icon the exe uses ──────────────────────────────────────
echo  Generating brand icon...
if not exist assets mkdir assets
python -c "import theme; theme.ensure_brand_ico('assets/cait.ico')"
if errorlevel 1 (
    echo  [!] Icon generation failed. Is Pillow installed in the venv?
    pause
    exit /b 1
)

:: ── Clean previous build outputs ──────────────────────────────────────────────
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist

:: ── Build the one-folder bundle ───────────────────────────────────────────────
echo.
echo  Building (this takes a few minutes the first time)...
echo.
pyinstaller cait-whisper.spec --noconfirm
if errorlevel 1 (
    echo.
    echo  [!] Build failed. Scroll up for the error.
    echo      Common fixes are noted at the top of cait-whisper.spec.
    pause
    exit /b 1
)

:: ── Drop a friendly readme into the bundle folder ─────────────────────────────
if exist packaging\READ_ME_FIRST.txt copy /y packaging\READ_ME_FIRST.txt "dist\cait-whisper\READ ME FIRST.txt" >nul

:: ── Zip it for the Releases page ──────────────────────────────────────────────
echo.
echo  Zipping...
powershell -NoProfile -Command "Compress-Archive -Path 'dist/cait-whisper/*' -DestinationPath 'dist/cait-whisper-windows.zip' -Force"

echo.
echo  ================================================
echo   Done.
echo.
echo   Test it:   "dist\cait-whisper\Cait Whisper.exe"
echo   Ship it:   dist\cait-whisper-windows.zip
echo              (upload to the GitHub release)
echo  ================================================
echo.
pause
