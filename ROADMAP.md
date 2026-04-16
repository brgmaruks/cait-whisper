# Roadmap

Where cait-whisper is headed. This is a living document and reflects current thinking, not binding commitments.

## Vision

Transform cait-whisper from a dictation tool into a **voice interface for Windows**. Keep it free, local, and private. Build the things paid competitors can't or won't.

---

## v2.0 - Voice Commands + Selection-Aware Mode

**Status:** Shipped (2026-04-16)

The product gains a second mode. In COMMAND mode, you can do more than dictate.

**Highlights:**
- **PURE / COMMAND toggle** - a right-click menu item. PURE is the default and matches v1.x exactly. COMMAND unlocks the rest.
- **Selection-aware** - cait-whisper detects whether text is selected when you start speaking. Rewrite in place if it is, insert if it isn't.
- **Voice commands** - say "new paragraph", "delete the last sentence", "capitalize that". Fast-path regex for common commands, local LLM fallback for natural variations.
- **In-place rewriting** - select a paragraph, say "make this more formal" or "make this shorter". The selection gets rewritten and replaces itself.

The demo: select a paragraph, say "make this less formal", watch it rewrite. No cloud. No subscription.

---

## v2.1 - Two-Pass Transcription

**Status:** Shipped (2026-04-16)

The fastest engine pastes instantly. The most accurate engine runs in the background on the same audio. If the slower pass produces a meaningfully better result, you get a toast with a one-keystroke option (`Alt+Shift+Z`) to swap it in.

Moonshine's latency for everything that came out right. Whisper's accuracy for everything that didn't. No mode switch required.

---

## v2.2 - Retroactive Capture

**Status:** Shipped (2026-04-16)

`Ctrl+Win+B` grabs the **last ~15 seconds** of audio and transcribes it. For the "wait, I just said something useful" moments. Always-on rolling buffer (~1.3 MB resident), zero change to existing workflows. Retroactive captures run through the full pipeline: spoken punctuation, dictionary, auto-learn, two-pass.

---

## v2.3 - Screen-Context Capture

**Status:** Shipped (2026-04-16)

In COMMAND mode, cait-whisper can OCR the region near your cursor and feed the text to the LLM classifier as context. Look at a PR, say "write a short approving comment but ask about test coverage". The model actually knows what the PR says.

Fully local OCR via RapidOCR (ONNX). No images, no extracted text, no anything leaves the machine. Opt-in via right-click menu; requires the optional `rapidocr-onnxruntime` package (~50 MB).

---

## Beyond v2.x

Ideas being considered, not committed to:

- **macOS and Linux support** - the core logic is platform-agnostic, but the hotkey system and native integrations are Windows-only today. Community contributions here are especially welcome.
- **Encrypted dictionary sync** - share your personal dictionary across machines, with client-side encryption so even the sync server can't read it.
- **Per-app profiles** - different engines, dictionaries, and behaviors depending on which app is focused.
- **Voice-activated launcher** - "Cait, open Notion" without touching the keyboard.

If there's something you'd love to see, open a [Discussion](https://github.com/brgmaruks/cait-whisper/discussions).

---

## Principles

Every decision on this roadmap is weighed against five commitments:

1. **Free forever.** No paywalls on core functionality.
2. **Fully local.** Your voice never leaves your machine.
3. **Respect existing workflows.** New features default off. Upgrades never break old habits.
4. **Function over form.** Polish matters, but capability matters more.
5. **Build in public.** Plans live in this file. Progress lives in the changelog.
