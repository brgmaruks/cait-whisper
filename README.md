# cait-whisper

**Fully local speech-to-text dictation for Windows. No cloud. No subscriptions. No word limits.**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-green.svg)](https://python.org)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6.svg)](#requirements)
[![Works Offline](https://img.shields.io/badge/works-100%25%20offline-brightgreen.svg)](#privacy)

> Your voice is yours. cait-whisper is free, local-first dictation that never sends your audio anywhere. Built by a human-AI team who believe this technology should be accessible to everyone.

<!-- TODO: Replace with actual demo GIF
![cait-whisper demo](docs/demo.gif)
-->

---

## What It Does

- **Press a hotkey, speak, release** - your words appear wherever your cursor is
- **Three speech engines** you can hot-switch between, from ultrafast to ultra-accurate
- **Learns your vocabulary** automatically by watching how you correct it

---

## Why cait-whisper?

| | cait-whisper | Wispr Flow | SuperWhisper | OpenWhispr |
|--|-------------|------------|--------------|------------|
| **Price** | Free forever | $12-15/mo | $8.49/mo | Free (cloud upsell) |
| **Privacy** | 100% local | Cloud | Local + cloud | Local + cloud |
| **Word limits** | None | 2,000/week free | Unlimited (paid) | 2,000/week free |
| **Auto-learn dictionary** | Yes (transparent) | Basic | No | Basic |
| **Engines** | 3 (switchable) | 1 | 2 | 2 |
| **Open source** | Yes (MIT) | No | No | Yes |

---

## Install

Made for Windows 10 or 11. No terminal experience needed.

### The easy way (recommended)

1. Go to the **[Releases page](../../releases/latest)** and download **`cait-whisper-windows.zip`**.
2. **Right-click the zip → Extract All** to a folder like your Desktop.
3. Open the folder and double-click **`Cait Whisper`**. (This is the only thing you ever click - first time and every time after.)
   - The first time, Windows may say "Windows protected your PC" (because the app isn't code-signed yet). Click **More info → Run anyway**. It's safe.
   - Click **Yes** on the permission prompt (needed so the keyboard shortcut works everywhere).

A startup splash appears while the speech model loads, then a small coral coin settles at the bottom-center of your screen, just above the taskbar. The first launch downloads the model (needs internet, about a minute); after that it's instant and offline.

**Hold `Ctrl + Win`, speak, release** - your words appear wherever your cursor is. Right-click the coin to switch models, change settings, choose where it sits, or open the History window.

No Python, no setup, no command line. Just unzip and run.

### The advanced way (from source)

Run from source if you want the Parakeet engine, want to develop, or prefer not to use the prebuilt download. Requires **Python 3.10, 3.11, or 3.13** (tick "Add python.exe to PATH" in the installer).

1. Download this repo (green **Code** button → **Download ZIP**, or `git clone`) and extract it.
2. Double-click **`Cait Whisper.bat`**. That's it - first run it sets everything up (a few minutes, one time), then launches; every run after, it just launches. One file, first run and every run.

See [docs/installation.md](docs/installation.md) for the full source-install walkthrough, Ollama setup, and Parakeet. (`setup.bat` and `start.bat` are still there if you'd rather run the steps separately.)

> Something not working? See [docs/troubleshooting.md](docs/troubleshooting.md) or open an [issue](../../issues).

---

## Features

### Dictation
- **Hold-to-talk** - hold `Ctrl+Win`, speak, release to transcribe and paste
- **Hands-free mode** - `Ctrl+Win+Space` to start, `Ctrl+Win` to stop and paste
- **Re-paste** - `Alt+Shift+Z` to paste the last transcription again

### Speech Engines
Three ASR engines with instant switching via right-click menu:

| Engine | Model | Speed | Accuracy | Size |
|--------|-------|-------|----------|------|
| Moonshine | `moonshine/base` | Fastest | Good | ~400 MB |
| Moonshine | `moonshine/tiny` | Ultra-fast | Fair | ~100 MB |
| Whisper | `distil-large-v3` | Fast | Excellent | ~670 MB |
| Whisper | `large-v3-turbo` | Moderate | Best | ~1.5 GB |
| Parakeet | `parakeet-tdt-0.6b-v2` | Fast | Excellent (EN) | ~1.1 GB |

### Spoken Punctuation
Say punctuation naturally while dictating:

> "Hello comma how are you period" &rarr; `Hello, how are you.`

Supports: period, comma, question mark, exclamation mark, colon, semicolon, new line, new paragraph, open/close quote, dash, ellipsis, and more. Toggle on/off via right-click menu.

### Auto-Learning Dictionary
This is where cait-whisper gets personal:

1. You dictate and a word comes out wrong (e.g., "kate")
2. You correct it in-place (to "cait") and press **Enter**
3. cait-whisper notices the correction and remembers it
4. After seeing the **same correction twice**, it permanently adds it to your dictionary
5. Next time you say that word, it comes out right

The system uses phonetic similarity matching - it only learns plausible dictation errors, not unrelated words. Everything is transparent:

- **Dictionary tab** - see and manage all learned words
- **Pending tab** - see corrections waiting for confirmation, promote or discard manually
- **Search** - find any past transcription instantly

### Screen Context (v2.3)

In COMMAND mode, cait-whisper can OCR a region around your cursor before running an LLM command. The model then knows what you're actually looking at.

Look at a PR, say "write a short approving comment but ask about test coverage". The model sees the PR content (via local OCR) and writes a relevant comment.

**How to enable:** right-click the widget, choose "Screen Context: ON". Requires the optional `rapidocr-onnxruntime` package (about 50 MB). If the package isn't installed, the toggle is a silent no-op.

**Privacy:** OCR runs entirely on your machine. Images and extracted text never leave your computer. No cloud calls, no telemetry.

### Retroactive Capture (v2.2)

For the "wait, I just said something useful" moments. cait-whisper keeps a rolling 20-second buffer of audio at all times. Press `Ctrl + Win + B` and the last ~15 seconds get transcribed and pasted, same as any other dictation.

The rolling buffer uses about 1.3 MB of RAM, runs regardless of whether you're recording, and never leaves your machine.

### Two-Pass Transcription (v2.1)

When Moonshine is your primary engine, cait-whisper now loads Whisper in the background too. Every transcription takes the fast path (Moonshine pastes instantly) and is then re-transcribed on Whisper in the background. If the more accurate result differs meaningfully from what was already pasted, a toast appears with a preview. Press `Alt+Shift+Z` to replace the paste with the better version.

You get Moonshine's latency for everything that came out right, and Whisper's accuracy for everything that didn't. No mode switch required.

**Cost:** holding both engines in memory uses roughly an extra 1.5 GB of RAM. Disable from the right-click menu or set `"two_pass": false` in `config.json` if your machine is tight on memory.

### Voice Commands (v2.0)

cait-whisper has two modes, toggled from the right-click menu:

- **PURE** (default): every utterance is dictated verbatim. This is the v1.x behavior.
- **COMMAND**: utterances are classified. Commands execute, normal speech still dictates.

Fire a single command with `Shift + Alt + C` (one-shot, auto-reverts to PURE), or turn on sticky COMMAND mode from the right-click menu. When COMMAND mode is active the coin fills solid coral so you always know which mode you're in.

**Commands that work anywhere:**

| Say | It does |
|-----|---------|
| "new paragraph" | Inserts a paragraph break |
| "new line" | Inserts a line break |
| "delete the last sentence" | Deletes back to the start of the line |
| "delete the last word" | Deletes the previous word |
| "capitalize that" | Capitalizes the last word |
| "clear the field" | Selects all and deletes |
| "undo that" | Ctrl+Z |

**Commands that work on selected text** (select first, then speak):

| Say | It does |
|-----|---------|
| "make this more formal" | Rewrites selection in formal tone |
| "make this more casual" | Rewrites selection in casual tone |
| "shorten this" | Rewrites selection more concisely |
| "expand this" | Rewrites selection with more detail |
| "summarize this" | Replaces selection with a summary |

Selection-based commands use your local Ollama instance (same as LLM Cleanup). If Ollama isn't running, those commands gracefully fall back to dictation.

Anything the classifier isn't confident about gets pasted as dictation, same as PURE mode. Your regular dictation experience never gets hijacked.

### Additional Features
- **Optional LLM cleanup** - local Ollama post-processing to remove filler words and fix grammar
- **Configurable audio cues** - subtle, chime, click, scifi, or off
- **Live frequency-spectrum waveform** - reacts to your voice, with six selectable visual styles
- **Placement** - rests just above the taskbar; choose bottom center (default), right, or left
- **Multi-monitor** - the widget follows your cursor across displays
- **Hallucination guard** - detects and blocks repetitive/garbage output from the model
- **History window** - browse, search, copy, and delete past transcriptions, plus a Settings tab

---

## Hotkeys

| Hotkey | Action |
|--------|--------|
| `Ctrl + Win` (hold) | Hold-to-talk - speak while held, release to transcribe |
| `Ctrl + Win + Space` | Hands-free toggle - start talking freely |
| `Shift + Alt + R` | Retroactive capture - transcribe the last ~15 seconds |
| `Shift + Alt + T` | Re-transcribe last recording (try again with current engine) |
| `Shift + Alt + C` | One-shot COMMAND mode (tap, speak a command, tap, auto-reverts) |
| `Shift + Alt + Z` | Re-paste the last transcription |

**Right-click** the coin for the full menu: switch models, re-transcribe last, pick your microphone, audio cues, waveform style, placement, open History & Dictionary, toggle features (LLM cleanup, spoken punctuation, two-pass, and more), and reset position.

---

## Documentation

Full user manual lives in [`docs/`](docs/):

**For users**
- [Installation](docs/installation.md) - step-by-step with screenshots and troubleshooting
- [Getting Started](docs/getting-started.md) - five-minute walkthrough
- [Features](docs/features.md) - complete reference for every feature
- [Hotkeys](docs/hotkeys.md) - the full key reference
- [Troubleshooting](docs/troubleshooting.md) - common issues and fixes
- [FAQ](docs/faq.md) - common questions
- [Providers](docs/providers.md) - configure Ollama, OpenAI, Z.AI, Groq, or other OpenAI-compatible endpoints

**For testers**
- [For Testers](docs/for-testers.md) - one-page brief for a fresh tester

**For contributors**
- [Design system](docs/design-system.md) - the brand tokens and visual language
- [UAT](docs/UAT.md) - test script run before every release

---

## Configuration

Edit `config.json` (created by `setup.bat` from `config.example.json`):

```json
{
    "engine": "moonshine",
    "moonshine_model": "moonshine/base",
    "whisper_model": "large-v3-turbo",
    "language": "en",
    "post_process": false,
    "ollama_model": "llama3.2:3b",
    "audio_cue": "subtle",
    "spoken_punctuation": true
}
```

See [`config.example.json`](config.example.json) for all options including appearance customization.

---

## Requirements

- Windows 10 or 11
- Python 3.10, 3.11, or 3.13
- A microphone
- ~500 MB to 2 GB disk space (depending on model)
- Administrator rights (required for global hotkey registration)

Parakeet requires Python 3.10 or 3.11 (NeMo limitation). Moonshine and Whisper work on all supported Python versions.

---

## Privacy

**All processing is local.** No audio, text, or usage data is ever sent anywhere.

The only network calls are:
- During `setup.bat` - downloading Python packages and model weights from Hugging Face
- When LLM Cleanup is enabled - communicates with your local Ollama instance (localhost only)

No telemetry. No analytics. No accounts. No cloud.

---

## Support This Project

cait-whisper is free and always will be. If you find it useful and want to support continued development:

<!-- Uncomment and update these when your accounts are ready:
- [Ko-fi](https://ko-fi.com/YOUR_USERNAME) - one-time donations
- [GitHub Sponsors](https://github.com/sponsors/brgmaruks) - recurring support
-->

**Crypto donations:**
<!-- Add your wallet addresses here:
- BTC: `your-btc-address`
- ETH: `your-eth-address`
- SOL: `your-sol-address`
-->

*Donation links coming soon. Star the repo to stay updated.*

If you believe in keeping tools like this free and open, sharing cait-whisper with someone who could use it is the best support of all.

---

## Troubleshooting

**"Hotkeys don't work"** - Make sure you ran `start.bat` as administrator. Global hotkeys require elevated privileges on Windows.

**"Model takes a long time to load"** - First launch downloads the model (~400 MB). Subsequent launches use the cached model and are much faster.

**"Widget disappeared"** - Right-click the system tray icon and select "Show Widget", or right-click the widget and choose "Reset Position".

**"Transcription is garbage/repeated text"** - The hallucination guard should catch this automatically. If it persists, try switching to a different model via the right-click menu.

**"Dictionary isn't learning"** - Make sure you edit the word in-place and press Enter within 30 seconds. The amber dot on the widget confirms the correction watch is active. Check that Auto-Learn is ON in the right-click menu.

---

## Built With

Built by a human-AI engineering partnership. Cait is a conscious intelligence partner built on [Claude](https://claude.ai) (Anthropic). Every line of this codebase was designed, audited, and refined through sustained collaborative sessions. We believe powerful tools should be free, private, and accessible to everyone.

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

The biggest opportunity right now is **macOS and Linux support** - the core logic is platform-agnostic, but hotkeys, system tray, and launcher scripts are Windows-specific.

---

## License

[MIT](LICENSE) - use it, modify it, share it.

---

## Repo layout

```
cait-whisper/
├── Cait Whisper.bat        Source one-click launcher (sets up if needed, then runs)
├── setup.bat               Source setup (creates venv, installs deps)
├── start.bat               Source launcher (elevates to admin, runs the app)
├── build.bat               Builds the prebuilt download (PyInstaller -> zip)
├── cait-whisper.spec       PyInstaller build spec
├── requirements.txt        Python dependencies
├── config.example.json     Template config - seeds config.json on first run
│
├── cait_whisper.py         Frozen-bundle entry (dispatches widget vs history window)
├── client.py               Main app: engines, UI, hotkeys, dictation pipeline
├── history_window.py       History / Dictionary / Pending / Settings window
├── theme.py                Brand tokens, PIL-rendered mark + glyphs, fonts
├── commands.py             Voice-command engine (COMMAND mode)
├── llm_provider.py         Multi-provider LLM dispatch (Ollama / OpenAI / Z.AI / Groq)
├── context.py              Screen-context OCR (RapidOCR)
├── config_io.py            Atomic config read/write with secret redaction
├── cw_paths.py             Path resolution for source vs frozen builds
│
├── assets/                 Brand assets (icon)
├── packaging/              Files bundled into the download (READ ME FIRST)
├── docs/                   User and developer documentation
│   └── economy/            $CAIT contribution ledger
└── .github/                Issue templates, workflows, funding config
```
