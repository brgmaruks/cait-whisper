# Installation

cait-whisper is a Windows-only tool. It runs fully locally - no cloud, no accounts, no subscriptions.

There are two ways to install: the **prebuilt download** (easiest, no Python) and the **source install** (for developers and the Parakeet engine).

## Easy: prebuilt download (recommended)

1. Go to the [Releases page](../../releases/latest) and download **`cait-whisper-windows.zip`**.
2. Right-click the zip → **Extract All** to a folder (your Desktop is fine).
3. Open the folder and double-click **`Cait Whisper`**. This is the only thing you ever click - first run and every run after.
   - First time only, Windows may show "Windows protected your PC" because the app isn't code-signed yet. Click **More info → Run anyway**.
   - Click **Yes** on the admin prompt (needed so the global Ctrl+Win hotkey works).

The first launch downloads the speech model (needs internet, about a minute). After that it's instant and offline. No Python, no setup, no command line.

**Requirements**: Windows 10 or 11, a microphone, and ~1 GB of free disk space. The download ships the Moonshine and Whisper engines; Parakeet is source-install only.

## Advanced: install from source

Use this if you want the Parakeet engine, want to develop, or prefer not to use the prebuilt download.

**Requirements**

- **Windows 10 or 11**
- **Python 3.10, 3.11, or 3.13** (Parakeet engine requires 3.10 or 3.11 specifically)
- **A microphone**
- **500 MB to 2 GB of disk space** depending on which ASR engine you use
- **Administrator rights** for global hotkey registration

**One launcher (recommended)**

1. Clone or download this repository to a folder of your choice.
2. Double-click **`Cait Whisper.bat`**. First run, it sets everything up; every run after, it just launches. One file, first run and every run.

What the first run does:
   - Checks that Python is installed (offers to install via winget if missing)
   - Creates a Python virtual environment in `venv/`
   - Installs all core packages from `requirements.txt`
   - Asks whether you want Parakeet (NVIDIA NeMo) and Ollama (voice commands / LLM cleanup)
   - Creates `config.json` from the example
   - Then launches the app (accept the UAC prompt - needed for the global hotkey)

The first launch also downloads the ASR model weights (~200 MB for Whisper distil-small.en, the default). After that everything is local and cached.

**Prefer the steps separately?** Run `setup.bat` once, then `start.bat` each time - `Cait Whisper.bat` just chains those two for you.

### Building the prebuilt download (maintainers)

The `cait-whisper-windows.zip` on the Releases page is produced from a source checkout with `build.bat`, which runs PyInstaller (see `cait-whisper.spec`) and zips the result. Run it from a working source install; the zip lands in `dist/`.

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

## LLM provider (Ollama or remote)

cait-whisper uses an LLM for:

- **Voice commands that rewrite text** ("make this more formal", "shorten this", "summarize this")
- **Screen context** ("summarize what you see")
- **LLM cleanup** (optional post-processing of transcriptions)

You have two choices:

### Option 1: Local Ollama (default, fully private)

Recommended if you value privacy or have decent CPU/GPU. All inference stays on your machine.

Without Ollama, the regex-based commands still work ("new paragraph", "delete the last sentence", etc.). Selection-based and screen commands silently fall back to plain dictation.

### Option 2: Remote OpenAI-compatible endpoint (faster, paid or self-hosted)

Recommended if local Ollama feels slow on your hardware (typical Ollama latency: 1-3s per rewrite). cait-whisper supports any OpenAI-compatible endpoint:

- **Z.AI** (Zhipu GLM models)
- **Groq** (very fast Llama / Mixtral)
- **Together AI**, **OpenAI**, **DeepSeek**
- **Self-hosted vLLM** behind your firewall
- **Remote Ollama** over Tailscale or any HTTPS endpoint

See [providers.md](providers.md) for setup details and example configs.

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
