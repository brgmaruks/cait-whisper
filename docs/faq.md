# FAQ

**Does cait-whisper send my voice to the cloud?**

No. Everything runs locally. The only network activity is:
- During `setup.bat` when pip fetches packages and the first launch when the ASR model weights download from Hugging Face.
- When "LLM Cleanup" is ON, communication with your local Ollama instance (localhost only).

There is no telemetry, no analytics, no account.

**Which ASR engine should I use?**

For most users: Moonshine (base) is the default because it's fastest and good enough. With two-pass transcription enabled (v2.1+), Whisper runs in the background and offers a better transcription whenever Moonshine gets it wrong, so you don't have to choose.

For English-only perfectionists: Parakeet is the most accurate but needs Python 3.10 or 3.11 specifically.

For other languages: Whisper large-v3-turbo has strong multilingual support.

**Why Windows only?**

cait-whisper depends on a few Windows-specific APIs for global hotkeys, UI Automation, and the tray icon. The ASR engines themselves are cross-platform. A macOS or Linux port would require swapping those integration layers but not the core. Community contributions welcome.

**Can I use a different LLM model?**

Yes. Set `"ollama_model"` in `config.json` to any model you've pulled with `ollama pull <name>`. Smaller models like `llama3.2:3b` (default) are faster but less accurate at classification. Larger models like `llama3.1:8b` or `qwen2.5:7b` are slower but better.

**Will this work offline?**

Yes, after the initial setup. Model weights are cached locally. No internet needed for dictation, voice commands, or LLM features.

**How accurate is the auto-dictionary?**

The auto-dictionary has two safeguards against polluting with noise:
1. Phonetic similarity gate: the original and corrected words must sound alike.
2. Confidence threshold of 2: one correction alone does nothing; you must make the same correction twice.

In practice it's very conservative. If you want to add a word it refused to learn, do it manually from the Dictionary tab.

**Can I share my dictionary across machines?**

Copy `dictionary.json` from one machine to another. That's it.

Encrypted cloud sync is a possible future feature. Nothing is committed.

**Does this work with headsets / Bluetooth mics?**

Yes. cait-whisper uses the default Windows input device. Change it in Windows Sound settings and restart the app.

**Can I use this while on a call?**

Yes, but be aware: when the mic is being used by your call app, some systems give it exclusive access and cait-whisper won't get any audio. Check Windows microphone privacy settings if recordings come out silent during calls.

**What if I accidentally enable COMMAND mode in the middle of a sentence?**

The worst that happens is short dictated phrases might get interpreted as commands. Press `Shift + Alt + M` to switch back to PURE mode. If a command fired that you didn't want, "undo that" (or Ctrl+Z manually) usually fixes it.

**Why are some commands regex-matched and others LLM-classified?**

Regex is instant and reliable for phrases we can pattern-match exactly. The LLM handles natural variations we can't enumerate. This hybrid approach means the common case (regex) has zero latency, and the uncommon case (LLM) still works as long as Ollama is running.

**Why is the first OCR call so slow?**

First call loads the RapidOCR ONNX models from disk. Subsequent calls are much faster (100-300ms). The tradeoff: we don't keep the OCR engine in RAM when you're not using it.

**I found a bug / want a feature. How do I report it?**

Open a [GitHub issue](https://github.com/brgmaruks/cait-whisper/issues) or [discussion](https://github.com/brgmaruks/cait-whisper/discussions).

**Is there a mobile version?**

Not yet. iOS/Android is on the roadmap but not imminent.

**Can I donate?**

Yes, eventually. Ko-fi and crypto options will be live shortly. See the [README](../README.md) for the current state.
