# Hotkeys

All hotkeys are global. They work regardless of which application has focus.

## Core dictation

| Hotkey | Action |
|--------|--------|
| `Ctrl + Win` (hold) | Hold-to-talk. Speak while held, release to transcribe and paste. |
| `Ctrl + Win + Space` | Toggle hands-free mode. Press once to start, again to stop and paste. |

## Retrieval

| Hotkey | Action |
|--------|--------|
| `Shift + Alt + Z` | Re-paste the last transcription. Useful when the first paste landed in the wrong field. |
| `Shift + Alt + R` | Retroactive capture. Transcribes the last ~15 seconds of audio from the always-on rolling buffer. |

## Mode

| Hotkey | Action |
|--------|--------|
| `Shift + Alt + C` | One-shot COMMAND mode. Press to start recording, press again to stop. The utterance is classified, command executes, and the app auto-reverts to PURE. No toggle management needed. |

The right-click menu has "Sticky COMMAND mode: ON/OFF" for users who prefer a persistent mode where every utterance is classified without needing a hotkey per command.

## In the text field (while correction watch is armed)

| Hotkey | Action |
|--------|--------|
| `Enter` | Tells cait-whisper you've finished editing. It diffs your edit against the original and learns any words that were corrected. The dot pulses amber when the watch is armed. |

## Why these keys

- **Ctrl + Win** for primary input because both keys are on the same side of the keyboard (easy to hold), and the combo rarely collides with application shortcuts.
- **Shift + Alt + letter** for retrieval and mode because Windows reserves nothing in this space globally. Some apps like VS Code use these combos, but only when focused. cait-whisper receives the hotkey first because it's registered as global.
- `Z`, `R`, `M` were chosen for mnemonic reasons ("zap the last paste", "retroactive", "mode") and ergonomic clustering with Shift+Alt.

## Known conflicts

- **Ctrl + Win + B**: used by some Intel graphics drivers and Lenovo Vantage. cait-whisper does **not** use this.
- **Shift + Alt + letter** can be overridden by certain apps when focused (VS Code, Office). If a hotkey doesn't fire, try it with the target app out of focus first.

## Customizing

Hotkey customization is not yet exposed in the menu. If you need to change a hotkey, edit `client.py` directly - look for the `_on_key_event` function. Hotkey customization through config is on the roadmap.
