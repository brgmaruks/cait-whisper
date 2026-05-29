# Getting started

You've run `setup.bat`. Now what?

## First launch

1. Double-click `start.bat`. Accept the UAC prompt.
2. A small coin (a coral Φ-in-circle mark) appears at the bottom-center of your screen, just above the taskbar.
3. While the model loads, the coin breathes coral. The very first launch downloads the model weights, which can take up to a minute depending on your connection; after that it's cached and loads in a few seconds.
4. When the coin settles to a quiet gray Φ and flashes coral once, you're ready.

## Your first dictation

1. Open Notepad, or click into any text field anywhere (email, chat, doc, form).
2. **Hold `Ctrl + Win` and speak.** The coin stretches into a pill showing a live waveform that reacts to your voice.
3. **Release.** A short delay (less than a second for Moonshine, a couple of seconds for Whisper), then your words appear.

That's it. This is the core experience. Every other feature is optional.

## Hands-free for longer dictation

If you're dictating a paragraph or an email, holding the keys gets tiring. Use hands-free mode:

1. Press `Ctrl + Win + Space`. The widget switches to an expanded state with cancel (✕) and stop (⏺) buttons.
2. Speak freely. Pause for breath as much as you want.
3. Press `Ctrl + Win + Space` again to stop and paste.

## Re-paste the last thing

If the paste landed in the wrong window, or you accidentally selected something else and the paste replaced it, press `Shift + Alt + Z` to re-paste the last transcription.

## Retroactive capture ("I just said something useful")

The mic is always listening to a rolling 20-second buffer. If you just finished saying something good, press `Shift + Alt + R` within 15 seconds to transcribe it.

## Teach it your words

When a word comes out wrong, just correct it in place and press **Enter**. Example:

- You say "Cait"
- It pastes "Kate"
- You edit it to "Cait" and press Enter
- The coin turns **amber and pulses**, telling you it's watching (hover it and the status reads "Waiting to learn")
- Do the same correction again. On the second time the word gets promoted to your personal dictionary. From then on, "Kate" automatically becomes "Cait" whenever cait-whisper hears it.

You can see and manage the dictionary via the right-click menu -> History & Dictionary.

## Voice commands (COMMAND mode)

cait-whisper has two modes:

- **PURE mode** (default): the coin is a quiet gray Φ. Everything you say becomes text.
- **COMMAND mode**: the coin fills solid coral. Short utterances are classified as commands and executed.

**For a single command**, press `Shift + Alt + C` (one-shot: speak one command, then it reverts to PURE automatically). **For sticky COMMAND mode**, right-click the coin and toggle "Sticky COMMAND mode".

In COMMAND mode you can say:

- "new paragraph", "new line"
- "delete the last sentence", "delete the last word"
- "capitalize that"
- "clear the field"
- "undo that"

And with text selected first:

- "make this more formal" / "make this more casual"
- "shorten this" / "expand this"
- "summarize this"

Selection-based commands require Ollama. See [installation.md](installation.md).

## Hover for status at a glance

Move your cursor over the coin. A card fades in with a live status pill in the top-right (Ready, Resting, Listening, Waiting to learn, and so on), your engine, every feature's state in a compact two-column grid, and a "Last paste" section showing the full text of what you last dictated. Move the cursor away and it disappears.

## Right-click for everything else

Right-click the coin to see:

- Switch Model (Moonshine, Whisper variants, Parakeet)
- Re-transcribe last (try the saved audio on a different model)
- Microphone (pick your input device)
- Audio Cues (subtle, chime, click, scifi, off)
- Waveform (six visual styles for the recording strip)
- Placement (bottom center, bottom right, bottom left)
- History & Dictionary (separate window, with the Settings tab)
- View Log File
- All feature toggles (Sticky COMMAND mode, Two-Pass, Screen Context, LLM Cleanup, etc.)
- Reset Position

## Where to go next

- [Features](features.md) for a complete guide to every feature
- [Hotkeys](hotkeys.md) for the full key reference
- [Troubleshooting](troubleshooting.md) when something isn't working
- [FAQ](faq.md) for common questions
