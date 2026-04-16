# Changelog

All notable changes to cait-whisper will be documented in this file.

## [2.2.0] - 2026-04-16

### Added
- **Retroactive capture** - new hotkey `Ctrl+Win+B` transcribes the last ~15 seconds of audio from a rolling buffer. Useful for "wait, I just said something useful" moments.
- **Always-on rolling buffer** - 20-second audio window maintained at all times, ~1.3 MB resident memory. Independent of the main recording buffer so hands-free recording is unaffected.

### Technical notes
- `_retro_frames` deque and `_retro_lock` are separate from the main recording buffer. The audio callback appends to both (conditionally to `_audio_frames` when `_recording`, always to `_retro_frames`).
- `_trigger_retro_capture()` snapshots the buffer, trims to the last 15 s, and feeds the frames list into the existing `_transcribe_and_paste()` pipeline. This means retroactive captures benefit from every downstream feature: spoken punctuation, LLM cleanup, dictionary, auto-learn, two-pass.
- The new hotkey refuses to fire while a recording or transcription is already in progress.

---

## [2.1.0] - 2026-04-16

### Added
- **Two-pass transcription** - when Moonshine is the primary engine, Whisper loads alongside it in the background. After each paste, Whisper re-transcribes the same audio on its own thread. If the result differs meaningfully, a toast appears and `Alt+Shift+Z` re-pastes the improved version.
- **Two-Pass menu toggle** - right-click menu item to enable/disable two-pass without editing config. Toggling OFF drops the background engine reference so GC can reclaim RAM.
- **`two_pass: true`** config key (default on when primary engine is Moonshine).

### Technical notes
- Background engine uses its own lock (`_bg_asr_lock`) and model reference (`_bg_asr_model`). This is intentional - using the main `_asr_lock` would block the next recording waiting on Whisper, which defeats the purpose.
- `_on_better_transcription()` filters out trivial differences (same text after lowercase + punct strip, or SequenceMatcher ratio >= 0.90). Only meaningfully-different results trigger a toast.
- Memory: ~1.5 GB extra RAM when both engines are loaded. Single-engine memory footprint is unchanged.
- When the primary engine is switched to Whisper or Parakeet, two-pass is a no-op (no value in running a second pass on a higher-accuracy primary).

---

## [2.0.0] - 2026-04-16

### Added
- **COMMAND mode** - new right-click menu toggle. In COMMAND mode, utterances are classified as dictation or commands. PURE mode (default) preserves v1.x behavior exactly.
- **Voice commands** - say "new paragraph", "delete the last sentence", "capitalize that", "clear the field", "undo that", and more. Regex fast-path for common commands (zero latency), local LLM fallback for natural variations.
- **Selection-aware rewriting** - select any text, then say "make this more formal", "shorten this", "expand this", or "summarize this". The selection gets rewritten in place via local Ollama.
- **Active window detection** - cait-whisper now knows which app has focus, used by the classifier to route commands appropriately.
- **Visual mode indicator** - the widget dot turns a subtle blue when in COMMAND mode.
- **`context.py`** - new module for Windows UI Automation and ctypes-based context detection. Degrades gracefully when pywinauto is unavailable.
- **`commands.py`** - new module housing the hybrid regex+LLM classifier and the command executor.
- **`ROADMAP.md`** - public roadmap for v2.x showing what's in progress, planned, and being considered.

### Changed
- `requirements.txt` now lists `pywinauto` for UI Automation support (used only in COMMAND mode).
- `config.example.json` has a new `command_mode: false` key. Existing configs still work; the key is optional and defaults to false.

### Safety and backward compatibility
- PURE mode is bit-identical to v1.1 behavior. No regressions for existing workflows.
- If the classifier is uncertain, the utterance is pasted as dictation rather than acted on. Confidence threshold is 0.7.
- If Ollama isn't running, LLM-based commands fail gracefully and fall back to dictation.

---

## [1.1.0] - 2026-04-16

### Fixed
- **Enter debounce** - rapid Enter presses no longer spawn parallel correction threads that double-count learned words
- **Atomic JSON writes** - pending_corrections.json and dictionary.json now use temp-file + rename to prevent corruption
- **Smart punctuation stripping** - dictionary learning now handles smart quotes, em dashes, and ellipsis inserted by spoken punctuation
- **ALL-CAPS preservation** - dictionary replacement now preserves full-uppercase words (e.g., "KATE" → "CAIT", not "Cait")
- **Dictionary regex** - word-matching pattern compiled once at module level instead of recompiled per call; fixed ambiguous character class

### Added
- **Raw ASR output in history** - history entries now include the original ASR output alongside the dictionary-applied text
- **Auto-Learn toggle** - right-click menu item to pause/resume dictionary auto-learning (persisted in config.json)
- **CI workflow** - GitHub Actions syntax check across Python 3.10, 3.11, and 3.13
- **GitHub Discussions** - enabled for questions and feature discussions
- **Competitor comparison** - README now includes feature comparison with Wispr Flow, SuperWhisper, and OpenWhispr
- **Troubleshooting section** - README now covers common issues and fixes

---

## [1.0.0] - 2026-04-15

Initial public release.

### Features
- **Hold-to-talk** dictation (`Ctrl+Win`) with instant paste
- **Hands-free mode** (`Ctrl+Win+Space`) for longer dictation sessions
- **Re-paste** last transcription (`Alt+Shift+Z`)
- **Three ASR engines** with hot-switching via right-click menu:
  - Moonshine ONNX (fastest, lightweight)
  - faster-whisper (most accurate, multi-language)
  - NVIDIA Parakeet NeMo (English specialist)
- **Auto-learning personal dictionary** - learns from your corrections with phonetic similarity matching and a 2-correction confidence threshold
- **Pending corrections tab** - see what the dictionary is learning, promote or discard entries manually
- **Spoken punctuation** - say "period", "comma", "new line", "question mark" etc. and get symbols
- **History window** with real-time search across all past transcriptions
- **Optional LLM cleanup** via local Ollama (removes filler words, fixes grammar)
- **Configurable audio cues** - subtle, chime, click, scifi, or off
- **Customizable widget appearance** - colors, transparency, size
- **Multi-monitor support** - widget follows your cursor across displays
- **Hallucination guard** - token-loop detection, WPM sanity check, n-gram repetition filter
- **Thread-safe architecture** - ASR lock for model switching, protected audio callback
- **Atomic JSON writes** - safe cross-process file coordination
- **Rotating log file** - 1 MB max, 3 backups

### Supported Models
- Moonshine: `moonshine/base`, `moonshine/tiny`
- Whisper: `distil-large-v3`, `large-v3-turbo`, `small`, `medium`, and more
- Parakeet: `nvidia/parakeet-tdt-0.6b-v2` (requires Python 3.10 or 3.11)
