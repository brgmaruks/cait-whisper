# For testers

You've been invited to test cait-whisper. Thank you. This page tells you exactly what to try, what to look for, and how to send feedback. No technical background needed.

cait-whisper is **a free Windows app that types what you say**. It runs entirely on your computer - your voice never leaves your machine.

## What you need

- A Windows 10 or 11 computer
- A microphone (built-in laptop mic is fine)
- About 15 minutes for the first install, then it's instant

## Install (5 minutes, one time)

Follow the three numbered steps in the [main README](../README.md#install-in-3-steps). Stop here when you see a small dark coin at the bottom-center of your screen, just above the taskbar.

Stuck on any step? Tell us where you got stuck - that's exactly the kind of feedback we need.

## Try these things in order

Open Notepad (or any app where you can type) and put your cursor in the text area.

### 1. Hold-to-talk
- **Hold `Ctrl + Win`** (the Windows key) - the coin lights up coral and a waveform appears
- **Speak a short sentence**: "Hello, this is a test of cait whisper."
- **Release the keys** - your sentence appears in Notepad

If it didn't work:
- Did the coin light up? If no, the hotkey isn't being registered (Windows admin issue - `start.bat` should have asked for admin permission)
- Did the waveform animate while you spoke? If no, the mic isn't picking up audio - right-click the coin → Microphone → pick the correct one
- Did nothing get typed? Check `cait-whisper.log` in the cait-whisper folder for an error message

### 2. Spoken punctuation
- Hold `Ctrl + Win` again
- Say: "Hello comma how are you period new paragraph I'm doing well period"
- Release

You should get:
```
Hello, how are you.
I'm doing well.
```

### 3. The History window
- Right-click the coin → **History & Dictionary**
- A window opens showing every transcription you've done

This is also where you change Settings (LLM provider, models, etc.) - the **Settings** tab at the top.

### 4. The auto-learning dictionary
- Dictate a word the system gets wrong (try saying a brand name or proper noun)
- Edit it in-place to fix the spelling, then press Enter within 30 seconds
- Repeat with the same correction one more time
- The third time you dictate that word, cait-whisper should get it right

Open the History window → **Dictionary** tab to see what it learned.

### 5. Switch models
- Right-click the coin → **Switch Model** → pick a different one
- The new model loads in the background (the coin flashes coral when ready)
- Dictate again - does the accuracy or speed feel different?

Try **Moonshine base** (fastest) and **Whisper distil-large-v3** (most accurate) at minimum.

## What we want to know

After 30 minutes of real use (write an email, take notes, draft a doc), tell us:

1. **What worked well?** Anything that felt surprisingly good?
2. **What got in the way?** Friction points, confusing bits, things that broke
3. **What would make you keep using it daily?** Missing features, must-haves
4. **What did the install feel like?** Where did you slow down or get stuck?

## When something breaks

The log file captures everything that goes wrong. To find it:

1. Open the cait-whisper folder
2. Find `cait-whisper.log` (right next to `start.bat`)
3. Open it in Notepad

When reporting a bug, please include:
- A short description of what you were doing
- The last 30-50 lines of `cait-whisper.log` (copy-paste is fine)
- Which model you were using (right-click the coin to see)

You can [open an issue on GitHub](../../issues/new) or just send the info directly to whoever invited you.

## A few things to know

- **The coin rests at the bottom-center of whichever monitor your cursor is on, just above the taskbar.** Move to another screen and it follows. Prefer a corner? Right-click → Placement → Bottom right or Bottom left.
- **Right-click the coin** for the full menu. **Left-click and drag** to move it to a custom spot on the current monitor.
- **The Φ-in-circle is the brand mark.** It's quiet (dark gray) at rest and **lights up coral when something is happening** (recording, ready signal, command mode). Hover it to see a status word (Ready, Resting, Listening, etc.).
- **The dot may disappear from your screen** if you put your cursor over it for too long. Right-click the system tray icon (small Φ in the Windows tray) → Show Widget to bring it back.
- **First launch takes 30-60 seconds** while the speech model loads. After that everything is instant.
- **`cait-whisper.log` is local to your machine.** It's just a text file you can open in Notepad. Sharing it is safe - it never contains the words you dictated, just system events.

## Privacy

cait-whisper sends nothing anywhere. No telemetry, no analytics, no audio uploads. The only network activity:
- During `setup.bat` - downloads Python packages and ASR model weights (one time)
- If you turn on **LLM Cleanup** with a remote provider (Z.AI, OpenAI, etc.) - your transcribed text goes to that provider for cleanup. **Off by default.** Local Ollama is the default LLM option.

Your microphone audio is never saved or transmitted. Each recording is processed in memory and discarded immediately.

---

Thank you for testing. Honest feedback (especially the negative kind) is the most valuable thing you can give us.
