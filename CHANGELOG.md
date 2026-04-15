# Changelog

All notable changes to cait-whisper will be documented in this file.

## [1.0.0] — 2026-04-15

Initial public release.

### Features
- **Hold-to-talk** dictation (`Ctrl+Win`) with instant paste
- **Hands-free mode** (`Ctrl+Win+Space`) for longer dictation sessions
- **Re-paste** last transcription (`Alt+Shift+Z`)
- **Three ASR engines** with hot-switching via right-click menu:
  - Moonshine ONNX (fastest, lightweight)
  - faster-whisper (most accurate, multi-language)
  - NVIDIA Parakeet NeMo (English specialist)
- **Auto-learning personal dictionary** — learns from your corrections with phonetic similarity matching and a 2-correction confidence threshold
- **Pending corrections tab** — see what the dictionary is learning, promote or discard entries manually
- **Spoken punctuation** — say "period", "comma", "new line", "question mark" etc. and get symbols
- **History window** with real-time search across all past transcriptions
- **Optional LLM cleanup** via local Ollama (removes filler words, fixes grammar)
- **Configurable audio cues** — subtle, chime, click, scifi, or off
- **Customizable widget appearance** — colors, transparency, size
- **Multi-monitor support** — widget follows your cursor across displays
- **Hallucination guard** — token-loop detection, WPM sanity check, n-gram repetition filter
- **Thread-safe architecture** — ASR lock for model switching, protected audio callback
- **Atomic JSON writes** — safe cross-process file coordination
- **Rotating log file** — 1 MB max, 3 backups

### Supported Models
- Moonshine: `moonshine/base`, `moonshine/tiny`
- Whisper: `distil-large-v3`, `large-v3-turbo`, `small`, `medium`, and more
- Parakeet: `nvidia/parakeet-tdt-0.6b-v2` (requires Python 3.10 or 3.11)
