# Installation

cait-whisper is a Windows-only tool. It runs fully locally - no cloud, no accounts, no subscriptions.

## Requirements

- **Windows 10 or 11**
- **Python 3.10, 3.11, or 3.13** (Parakeet engine requires 3.10 or 3.11 specifically)
- **A microphone**
- **500 MB to 2 GB of disk space** depending on which ASR engine you use
- **Administrator rights** for global hotkey registration

## Automated install (recommended)

1. Clone or download this repository to a folder of your choice.
2. Double-click `setup.bat`.
3. The installer will:
   - Check that Python is installed (offers to install via winget if missing)
   - Create a Python virtual environment in `venv/`
   - Install all core packages from `requirements.txt`
   - Ask whether you want to install Parakeet (NVIDIA NeMo)
   - Ask whether you want to install Ollama for voice commands and LLM cleanup (offers to install via winget)
   - Pull the default Ollama model if you said yes
   - Create `config.json` from the example

The first launch downloads the ASR model weights (~400 MB for Moonshine base, the default). After that everything is local and cached.

4. Double-click `start.bat` to launch. You may see a UAC prompt; accept it.

## Manual install

If you prefer to do it by hand:

```bat
cd cait-whisper
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
copy config.example.json config.json
start.bat
```

## Ollama (optional but recommended)

Ollama runs local language models. It's used by:

- **Voice commands that rewrite text** ("make this more formal", "shorten this", "summarize this")
- **Screen context** ("summarize what you see")
- **LLM cleanup** (optional post-processing of transcriptions)

Without Ollama, the regex-based commands still work ("new paragraph", "delete the last sentence", etc.). Selection-based and screen commands silently fall back to plain dictation.

**Install Ollama:**

- Option A: `winget install Ollama.Ollama` in PowerShell
- Option B: download the installer from https://ollama.com/download/windows

**Pull the default model:**

```bat
ollama pull llama3.2:3b
```

This is a small, fast model that handles command classification and text rewriting well. You can change which model cait-whisper uses by editing `config.json`:

```json
"ollama_model": "llama3.2:3b"
```

## Administrator rights

Windows requires elevated privileges to register global hotkeys. `start.bat` will prompt for UAC elevation automatically. If you want to skip the UAC prompt every time, see the scheduled task approach in `docs/troubleshooting.md`.

## Uninstall

Delete the folder. cait-whisper writes nothing outside it.

If you also installed Ollama:

- `winget uninstall Ollama.Ollama`
- Delete `%USERPROFILE%\.ollama` to remove downloaded models

## Next steps

- [Getting started](getting-started.md) - a five-minute walkthrough
- [Features](features.md) - everything cait-whisper can do
- [Hotkeys](hotkeys.md) - reference sheet
- [Troubleshooting](troubleshooting.md) - common issues and fixes
