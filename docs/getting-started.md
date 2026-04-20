# Getting started

You've run `setup.bat`. Now what?

## First launch

1. Double-click `start.bat`. Accept the UAC prompt.
2. A small dot appears somewhere near the bottom-right of your screen.
3. The dot will briefly flash green when the ASR model is loaded and ready (about 3-5 seconds on first launch).
4. When the dot is gray and sitting still, you're ready.

## Your first dictation

1. Open Notepad, or click into any text field anywhere (email, chat, doc, form).
2. **Hold `Ctrl + Win` and speak.** The dot will grow and show a waveform animation.
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
- The dot turns **amber and pulses**, telling you it's watching
- Do the same correction again. On the second time the word gets promoted to your personal dictionary. From then on, "Kate" automatically becomes "Cait" whenever cait-whisper hears it.

You can see and manage the dictionary via the right-click menu -> History & Dictionary.

## Voice commands (COMMAND mode)

cait-whisper has two modes:

- **PURE mode** (default, gray dot): everything you say becomes text.
- **COMMAND mode** (blue ring dot): short utterances are classified as commands and executed.

**Switch modes** with `Shift + Alt + M`, or right-click the dot and select "Mode: PURE" / "Mode: COMMAND".

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

Move your cursor over the dot. A small panel appears showing the current engine, mode, and every feature's state. Move the cursor away and it disappears.

## Right-click for everything else

Right-click the dot to see:

- Switch Model (Moonshine, Whisper variants, Parakeet)
- Audio cues (subtle, chime, click, scifi, off)
- History & Dictionary (separate window)
- View Log File
- All feature toggles (Mode, Two-Pass, Screen Context, LLM Cleanup, etc.)

## Where to go next

- [Features](features.md) for a complete guide to every feature
- [Hotkeys](hotkeys.md) for the full key reference
- [Troubleshooting](troubleshooting.md) when something isn't working
- [FAQ](faq.md) for common questions
