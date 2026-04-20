# Features

Every feature cait-whisper offers, what it does, when to use it, and how to turn it on or off.

## Dictation engines

cait-whisper supports three ASR engines. Switch between them from the right-click menu -> Switch Model. You can change at any time; the app briefly shows a "busy" state while loading the new model.

| Engine | Model | Speed | Accuracy | Best for |
|--------|-------|-------|----------|----------|
| **Moonshine** | moonshine/base | Fastest (~100ms) | Good | Quick chats, everyday dictation |
| **Moonshine** | moonshine/tiny | Ultra-fast | OK | Low-end machines |
| **Whisper** | distil-large-v3 | Fast (~500ms) | Excellent | Long-form writing, emails |
| **Whisper** | large-v3-turbo | Moderate (~2s) | Best | Anything precise |
| **Whisper** | small | Fast | Good | Balanced general-use |
| **Parakeet** | parakeet-tdt-0.6b-v2 | Fast | Excellent (EN) | English-only, Python 3.10/3.11 required |

## Two-pass transcription

When Moonshine is your primary engine, Whisper loads in the background. After each paste, Whisper re-transcribes the same audio on its own thread. If it produces a meaningfully different result, a blue toast appears on the widget with a preview. Press `Shift + Alt + Z` to swap in the better version.

You get Moonshine's latency most of the time and Whisper's accuracy whenever it matters.

- **Toggle**: right-click menu -> "Two-Pass: ON/OFF"
- **Cost**: ~1.5 GB extra RAM while both engines are loaded
- **No-op** when the primary engine is already Whisper or Parakeet

## Retroactive capture

cait-whisper keeps a rolling 20-second buffer of audio at all times, even when you're not actively recording. Press `Shift + Alt + R` and the last ~15 seconds get transcribed and pasted.

Great for the "wait, I just said something good" moment on a call, or when you want to re-dictate something a coworker just said out loud.

- **Memory cost**: ~1.3 MB resident
- **Privacy**: audio only lives in memory, never written to disk
- **Runs through the full pipeline**: same spoken punctuation, LLM cleanup, dictionary, auto-learn, two-pass as normal dictation

## Spoken punctuation

Say punctuation words out loud and they become symbols:

| You say | It writes |
|---------|-----------|
| "period" | . |
| "comma" | , |
| "question mark" | ? |
| "exclamation mark" | ! |
| "colon" | : |
| "semicolon" | ; |
| "new line" | \n |
| "new paragraph" | \n\n |
| "open quote" / "close quote" | " |
| "dash" | - |
| "ellipsis" | ... |

**Toggle**: right-click menu -> "Spoken Punct: ON/OFF".

## LLM cleanup (optional post-processing)

When ON, every transcription gets sent to your local Ollama instance. The model removes filler words ("um", "uh", "like", "so"), fixes obvious grammar issues, and adds missing punctuation. The raw transcription is preserved in the history window so you can see exactly what the model changed.

- **Toggle**: right-click menu -> "LLM Cleanup: ON/OFF"
- **Requires**: Ollama installed and running, a pulled model (`llama3.2:3b` by default)
- **Latency**: adds 0.5-2 seconds per paste depending on model size

## Auto-learning personal dictionary

When you correct a word and press Enter within 30 seconds of pasting, cait-whisper diffs your edit against the original. Word-level changes that sound phonetically similar become **pending corrections**. After you make the same correction twice, the entry is promoted to your permanent dictionary.

From then on, cait-whisper applies the dictionary to every transcription. "Kate" becomes "Cait", "llm" becomes "LLM", etc.

Design choices:
- **Phonetic similarity gate**: prevents learning unrelated words if you do a global rewrite
- **Confidence threshold of 2**: one stray correction doesn't pollute the dictionary
- **Case preservation**: KATE -> CAIT, Kate -> Cait, kate -> cait

**Manage the dictionary**: right-click menu -> "History & Dictionary". You can view promoted entries, pending candidates, and manually add or delete entries.

- **Toggle**: right-click menu -> "Auto-Learn: ON/OFF"
- **Note**: disabling auto-learn does not disable existing dictionary substitution. Those still apply.

## COMMAND mode

Toggle with `Shift + Alt + M` or right-click -> "Mode: PURE/COMMAND". The widget dot changes:

- **PURE** (default): filled dot `●`, gray, always idle color
- **COMMAND**: hollow ring `◎`, bright blue

In COMMAND mode, every utterance goes through a hybrid classifier:

1. **Regex fast-path**: instant match for common phrases like "new paragraph", "delete the last sentence"
2. **Selection regex**: if text is selected, phrases like "shorten this" or "make this more formal" are recognized
3. **Screen-context regex**: if screen context is enabled, phrases like "summarize what you see" work
4. **LLM fallback**: for short ambiguous utterances, Ollama is asked to classify. Confidence threshold 0.7.
5. **Dictation fallback**: anything not confidently a command is pasted as normal text

### Commands that work anywhere in COMMAND mode

| Say | It does |
|-----|---------|
| "new paragraph" | Two line breaks |
| "new line" | One line break |
| "delete the last sentence" | Selects to line start and deletes |
| "delete the last word" | Ctrl+Backspace |
| "capitalize that" | Selects last word, capitalizes first letter |
| "clear the field" | Ctrl+A then Delete |
| "undo that" | Ctrl+Z |
| "try again" | Meta-command, currently logged only |

### Commands that work on selected text

Highlight text first, then say:

| Say | It does |
|-----|---------|
| "make this more formal" | Rewrites selection in formal tone |
| "make this more casual" | Rewrites in casual tone |
| "shorten this" | Significantly shortens while preserving meaning |
| "expand this" | Expands with more detail |
| "summarize this" | Replaces selection with a one-or-two-sentence summary |

These require Ollama.

### Screen-context commands

When Screen Context is enabled and the classifier captures visible text near your cursor:

| Say | It does |
|-----|---------|
| "summarize what you see" | Pastes a brief summary of what's visible |
| "summarize this screen" | Same |
| "what's on the screen" | Same |
| "explain what you see" | Pastes a short explanation |

These require Ollama and the `rapidocr-onnxruntime` package.

## Screen context

In COMMAND mode, cait-whisper can OCR a 700x400 region around your cursor and pass the extracted text to Ollama as context. This enables screen commands (above) and richer LLM classification.

- **Toggle**: right-click menu -> "Screen Context: ON/OFF"
- **Requires**: `rapidocr-onnxruntime` (installed by setup.bat automatically)
- **Privacy**: OCR runs fully locally via ONNX. No images, no text, no anything leaves the machine. The 700x400 capture region is centered on your cursor so background apps aren't scraped.
- **Latency**: first OCR call is ~2 seconds (ONNX model init), subsequent ~100-300ms

## History and dictionary window

A separate window, launched from right-click -> "History & Dictionary".

- **History tab**: all past transcriptions with timestamps and the engine that produced them. Searchable. You can copy, delete, or inspect any entry. Each entry stores both the final pasted text and the raw ASR output, so you can see exactly what the dictionary or LLM changed.
- **Dictionary tab**: all learned words. Add manually with "Heard -> Replace with" fields, or delete existing entries.
- **Pending tab**: candidate corrections waiting to reach the confidence threshold. Promote or discard manually.

## Dev logs

When ON, the log file captures every decision the app makes: correction watch arming, clipboard probes, classifier opcodes, similarity checks, OCR results, etc. Use this when something's not working and you want to send us a log snippet, or diagnose an issue yourself.

- **Toggle**: right-click menu -> "Dev Logs: ON/OFF"
- **Log location**: `cait-whisper.log` in the app folder. Open via right-click -> "View Log File".
- **Rotation**: 1 MB max, 3 backups. Won't eat disk.

## Audio cues

Start-of-recording and end-of-transcription audio signals. Useful for confirming the app is listening when you can't see the dot.

- **Profiles**: subtle (default), chime, click, scifi, off
- **Change**: right-click -> "Audio Cues" submenu. Each profile has a "Test" option.

## Hallucination guard

The ASR models sometimes loop or generate junk from silence. cait-whisper catches this at three points:

1. **RMS gate**: if the recording is too quiet, skip ASR entirely
2. **WPM sanity**: if the output claims >400 words per minute, discard
3. **N-gram repetition**: if any 2-4 word sequence makes up >55% of the output, discard

Discarded recordings show a brief "no speech" indicator on the widget.

## Hover status card

Move your cursor over the widget. A small panel appears showing every feature's current state, the last transcription, and the active engine. Move the cursor away and it closes.

Designed for at-a-glance confirmation without hunting through right-click menus.

## Multi-monitor support

The widget respects which monitor your cursor is on and stays there across display changes. Drag it anywhere. Position is saved in `config.json` and survives restarts. Right-click -> "Reset Position" returns it to the bottom-right default.
