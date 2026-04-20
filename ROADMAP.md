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

## v2.4 - Stabilization, UX, and One-Shot Commands

**Status:** Shipped (2026-04-18)

Everything from UAT feedback: auto-dictionary actually works (the debounce flag was getting stuck permanently), voice commands fire even when their phrase overlaps with spoken-punctuation ("new paragraph"), hover status card on widget (multi-monitor aware via virtual screen bounds), dev-logs toggle for diagnostics, full docs folder. Renamed `Ctrl+Win+B` (conflicted with Intel graphics drivers) to `Shift+Alt+R`. Added `Shift+Alt+C` one-shot COMMAND mode: tap to record a command, tap again to execute, auto-reverts to PURE. Installer now offers Python and Ollama via winget. Model-switch sound. Manual widget placement now persists across restart.

---

## v2.5 - Remote Providers (Online ASR + LLM)

**Status:** Planned (PULLED FORWARD, top-priority)

The pain: local Ollama latency is noticeable on modest hardware (1-3 s per rewrite). Users who want their AI features to feel instant should be able to point cait-whisper at a faster backend without giving up the "local-first default" ethos.

**What this ships:**

- **LLM endpoint config**: `llm_provider` in config.json. Options:
  - `ollama` (default, local, what we have today)
  - `openai` (OpenAI-compatible - works for GPT-4, Groq, Together, Zhipu/Z.AI, DeepSeek, local vLLM, Jan's OpenAI-compatible server, self-hosted Ollama over HTTPS via Tailscale, etc.)
  - Just two provider types cover the world. Users put in a base_url + api_key + model name.
- **ASR endpoint config**: `asr_remote_url` for offloading transcription to a remote Whisper-compatible server (e.g. self-hosted faster-whisper-server, Groq Whisper, Deepgram, etc.). Local Moonshine/Whisper remain the default.
- **Per-feature provider choice**: some users want LLM cleanup local but command classification remote, or vice versa. Each feature gets its own provider pick.
- **Onboarding flow**: first-run prompt asks whether user wants fully-local, remote-only, or mixed. Sets sensible defaults. Changeable later via right-click menu.

**Why this beats current defer-to-roadmap approach:**
- Users like Marco already have their own Tailscale-reachable GPU servers. Blocking them on "use Ollama locally or nothing" is a bad bet.
- Z.AI / Zhipu, Groq, Together, OpenAI all work with the same OpenAI client library. Single HTTP client, many providers.
- Keeps the local-first default. Privacy-focused users change nothing.

---

## v2.5-plus - Productivity Panel: Timezones

**Status:** Planned

cait-whisper starts evolving from a speech-to-text tool into a voice-driven productivity command center. First add: timezones.

**Two surfaces, one underlying engine:**

1. **Tray cascade**: right-click the widget -> "Timezone" submenu with current times for each configured zone. One glance, no clicks. Always up to date because the menu rebuilds on every open.

2. **Popout panel tab**: the existing "History & Dictionary" popout window gains a new "Timezones" tab, sitting alongside History / Dictionary / Pending. This is the full worldtimebuddy.com experience:
   - Rows: each configured zone with label, offset, current time
   - Columns: 24-hour timeline strip per row
   - **Click any cell and that column highlights across every row** - the Marco-at-3pm-London use case that drove this feature in the first place
   - Drag to select a range for meeting-finding
   - Live clocks tick once per second
   - "Add zone" / "Remove zone" inline, persisted to `config.json`

3. **Voice commands** in COMMAND mode:
   - "what time is it in London" -> pastes "11:17 BST"
   - "convert 3pm to Madrid and Iasi" -> pastes the conversions
   - "format a meeting at 10am Kuala Lumpur" -> pastes a formatted multi-zone line

Stdlib `zoneinfo` does all the math. No new dependencies.

**Display preferences** (matching worldtimebuddy's top-right toggle):
- **am/pm vs 24h** time format (per-user, stored in `config.json`)
- **Date format** toggle (short date next to each zone)
- Both apply consistently across the tray cascade, the popout tab, and voice command output.

**Why a tab in the existing popout instead of a separate window:** as more productivity tools land (clipboard history, unit converter, calendar glance, etc.) we want one destination, not N scattered windows. The popout is already a separate process (`history_window.py`) so the main dictation path stays snappy regardless of how heavy the panel becomes.

**Hotkey** (proposed): `Shift + Alt + P` opens the panel directly.

---

## Command library expansion (rolls into v2.5 and v2.6)

One-shot COMMAND mode shipped in v2.4 works. Next step: expand the vocabulary.

**v2.5 (with online providers):**

- **Tier 1 — text editing (no LLM, instant)**: select all, copy/cut/paste, bold/italic/underline, indent/outdent, go to end/start/line/file, page down/up, save, find, next/previous tab.
- **Tier 3 — meta (no LLM, instant)**: cancel, open history, open dictionary, quit cait, reset position.

Both tiers are zero-latency and fit the one-shot UX perfectly. Ship together.

**v2.5-plus (after online providers land):**

- **Tier 4 — LLM transformations on selection**: translate to any language, fix grammar, active/passive voice, warmer/neutral/excited tone, bullet points, table, email format, slack format, simplify, extract action items.
- Two UX patterns to test: (a) user selects text FIRST then says "translate to Spanish" → LLM returns → pastes replacing selection; (b) selection detected automatically from UI Automation on command utterance. Pattern (a) is reliable; pattern (b) fails in apps without UIA text pattern. Ship pattern (a) as default, pattern (b) as a best-effort fallback.

**v2.6:**

- **Tier 2 — case transformations**: lowercase that, uppercase that, title case that. Small polish.
- **Tier 5 — screen-context commands** (needs v2.3 OCR + LLM): "draft a reply to this email", "summarize this article", "what is this code doing", "translate what you see to [language]".
- **Tier 7 — voice-native launchers**: "open Notion", "switch to Chrome", "new email". These need app-name resolution (by window title, executable, or user-configured aliases). Start with a user-configured map in config.json; fancier auto-discovery later.

**v2.7+:**

- **Tier 6 — calculation / conversions**: "calculate [expression]", "convert 100 USD to EUR", unit tables, timezone (handled by v2.5-plus panel).

**Discoverability** (every tier depends on this):

- Right-click → "Available Commands" opens a compact reference window listing every command grouped by tier. Each entry shows the trigger phrase + an example. Users can't use commands they don't know exist.
- Include "Print cheat sheet" option that generates a printable PDF of the command reference.
- First-run onboarding steps through the 8-10 highest-value commands interactively.

---

## v2.6 - Trigger Word Mode

**Status:** Planned

One-shot COMMAND mode (shipped in v2.4) covers the hotkey path. The remaining gap: fully voice-driven commands with no hotkey at all.

**Activate commands by saying a trigger word**: "[trigger], [command]". Default trigger: **Nova** (uncommon in daily speech, phonetically clear, two syllables, chosen by Marco as the beta default). Fully configurable in settings and surfaced at onboarding so users can pick their own if Nova doesn't fit ("Computer" for Star Trek fans, "Jarvis" for Marvel fans, etc.).

The trigger word gets stripped from the utterance before classification; the remainder is the command. If no command matches, the utterance falls through to dictation minus the trigger word.

Requires continuous background listening when the feature is on - probably best implemented as an extension to the retroactive rolling buffer with VAD-based utterance segmentation. This is a bigger piece of work than one-shot.

---

## Beyond v2.x

Ideas being considered, not committed to:

- **macOS and Linux support** - the core logic is platform-agnostic, but the hotkey system and native integrations are Windows-only today. Community contributions here are especially welcome.
- **Encrypted dictionary sync** - share your personal dictionary across machines, with client-side encryption so even the sync server can't read it.
- **Per-app profiles** - different engines, dictionaries, and behaviors depending on which app is focused.
- **Voice-activated launcher** - "Cait, open Notion" without touching the keyboard.
- **Custom ASR / LLM endpoints** - user-configurable remote providers. Point cait-whisper at a home server running Whisper on GPU (over Tailscale, LAN, or any HTTPS endpoint), or at a hosted API (Groq, Deepgram, Azure, etc.). Same for the LLM side - route Ollama-compatible calls to a beefier remote Ollama. Unlocks serious accuracy/speed without changing the local-first default for people who don't want it.
- **Multilingual dictation** - pick language per session or auto-detect. Whisper already handles 99+ languages; we just need the wiring: language picker in the menu, per-language dictionaries, spoken-punctuation tables per language. Gateway feature for non-English users.
- **Generic two-pass post-processing** - v2.1 two-pass only fires when Moonshine is primary. Generalize: any engine can be a "fast pass," any engine can be a "slow pass," independent of which is primary. Also pluggable post-processors - LLM cleanup, custom regex, remote refinement - that run in the background and surface an "improved version" toast. Makes the pattern a generic capability, not a Moonshine-specific feature.
- **Unified notification / HUD layer** - every mode change, every action (retroactive capture, command executed, two-pass swap, model switch, correction learned) deserves a brief top-of-screen text bubble. Right now we rely on the tiny dot color + widget-local toasts, which users miss. A dedicated transient overlay near the top of the screen would make the app's state and actions obvious without being intrusive.
- **UI refresh matching Claude Code / Anthropic aesthetic** - shared design system across the dot widget, hover card, right-click menu, history/dictionary window, and v2.5 productivity panel. Dark surface (#1A1A1C-ish), muted gray secondary text, single accent color, generous padding, monospace for code-ish content. One CSS-like constants module drives all windows so a palette change is one file edit. Current UI has drift (history window tab styling doesn't match widget toast styling doesn't match hover card).
- **More productivity panel tabs** - clipboard history, unit converter, calendar glance, currency. The panel becomes the destination for quick lookups without leaving the keyboard.
- **Voxtral engine experiment** - Mistral's 4B multimodal audio model (`Voxtral-Mini-4B-Realtime-2602`). Would live alongside Moonshine / Whisper / Parakeet as an opt-in experimental engine. Its real interest isn't transcription quality (Whisper is already excellent) but audio-native understanding - skipping the ASR + LLM hop for commands like "summarize what I just said" or "extract action items from this recording." Worth exploring once the current stack is stable. Notes: needs torch + transformers (~2 GB dep footprint), Mistral Research License restricts commercial use, CPU-only performance will be slow enough that GPU is recommended.
- **Ichigo engine experiment** ([janhq/ichigo](https://github.com/janhq/ichigo)) - Jan AI's open-source early-fusion audio LLM. Same audio-native design space as Voxtral but with a few advantages for our use case: GGUF weights (so it can run through llama.cpp / Ollama which we already integrate), Apache-licensed (no commercial restrictions), and smaller footprint. Would slot in as a second experimental audio-understanding engine next to Voxtral so we can benchmark the two honestly on real cait-whisper workloads. Same deferral reasoning applies: ship v2.4 and v2.5 first.
- **iOS and Android** - companion apps. iOS first.

If there's something you'd love to see, open a [Discussion](https://github.com/brgmaruks/cait-whisper/discussions).

---

## Principles

Every decision on this roadmap is weighed against five commitments:

1. **Free forever.** No paywalls on core functionality.
2. **Fully local.** Your voice never leaves your machine.
3. **Respect existing workflows.** New features default off. Upgrades never break old habits.
4. **Function over form.** Polish matters, but capability matters more.
5. **Build in public.** Plans live in this file. Progress lives in the changelog.
