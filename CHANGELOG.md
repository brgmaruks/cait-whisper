# Changelog

All notable changes to cait-whisper will be documented in this file.

## [2.5.6] - 2026-05-29

Widget motion + placement polish. A pass focused entirely on how the floating
widget looks and moves: a true coin<->pill morph, a real frequency-spectrum
waveform, placement options, and premium startup/processing/done animations.
The ASR pipeline is unchanged.

### Added
- **Coin <-> pill morph** via `SetWindowRgn`. The window is now clipped to an
  actual shape - a circle when idle, a stadium (pill) when active - so the
  resting coin appears to stretch into the recording strip. True geometric
  clipping, not the old color-key trick (which leaked magenta corners on some
  displays). Heights matched at 32px so there is no vertical jump.
- **Real FFT frequency-spectrum waveform** while recording. Each bar is a
  log-spaced frequency band across the voice range, laid out bass-center and
  symmetric so the strip blooms from the middle and reacts to the actual
  spectral content of your voice. Adaptive normalization + fast-attack/slow-
  release smoothing for a "peak meter" feel. Replaces the old amplitude-times-
  gaussian-times-random pulse.
- **Placement submenu** (right-click -> Placement): Bottom center (new
  default), Bottom right, Bottom left. Composes with cursor-follow; the strip
  expands symmetrically at center, leftward at right, rightward at left.
  Persists to config as `widget_placement`.
- **Premium startup animation**. The "warming up" state now runs a calm
  on-brand coral breathing bloom while the model loads (previously it drew a
  single blank frame and stopped - the loading state had no animation at all).
- **Hover-card status pill** (top-right): a live, color-coded word for what
  Cait is doing - Ready / Resting / Warming up / Listening / Transcribing /
  Waiting to learn / Command mode. The Ready-vs-Resting split tells you
  whether the next dictation is instant or has a brief model-wake.
- **Waveform style persistence** already shipped in 2.5.5; this release wires
  the FFT data through every style.

### Changed
- **Default placement is now bottom-center** (Wispr Flow / superwhisper
  convention) instead of bottom-right.
- **Widget rests just above the taskbar**. The vertical margin dropped from
  60px to 12px (it was floating far above the taskbar). Reset Position and the
  startup anchor now use the monitor work area so the dot never lands behind
  the taskbar.
- **Processing animation** is now an organic multi-wave flow (three sine waves
  at incommensurate frequencies) so it never visibly repeats - fixes the
  monotony of the old single looping ripple on long transcriptions.
- **Done animation** is a "gather to center and settle" (outer bars fall
  first, center resolves last) instead of a static full-height block.
- **State colors consolidated into the coral family.** Processing moved from
  MUSTARD to CORAL_SOFT (mustard is reserved for the correction-watch pulse);
  startup loading moved from INFO blue to CORAL_SOFT. Only live recording uses
  full-saturation CORAL, so the moment you are actually talking reads as
  primary. States are now distinguished by MOTION, not hue.
- **Active strip width is locked** across the record -> process -> done flow,
  so a hands-free session no longer shrinks from 240px to 168px mid-flow.
- **Hover card redesigned**: the 7 settings toggles are now a compact two-
  column grid (4 rows instead of 7) with values colored by state, freeing
  vertical room for a dedicated "Last paste" section that shows the full text
  wrapped over multiple lines (up to 320 chars) instead of a 37-char one-liner.

### Fixed
- **Hover card bled across the monitor bezel.** It clamped to the virtual-
  screen bounds (all monitors combined) instead of the widget's own monitor,
  so near a shared edge it spilled onto / was truncated by the neighbour
  screen. Now confined to the monitor the widget sits on.
- **Waveform bloomed during silence.** The adaptive normalization amplified
  background noise to full scale when you went quiet. Added a silence gate
  (RMS floor) so the strip rests flat until you actually speak.
- **Cross-monitor follow** edge cases from the placement rework verified;
  manual drag still overrides until the next placement pick or monitor hop.

## [2.5.5] - 2026-05-28

Headline: ASR pipeline is unchanged. Everything else got a full visual and UX overhaul so the app looks and feels like a 1.0 product instead of a tool-by-engineers.

### Added
- **`theme.py`** - single source of truth for every color, font, spacing token, glyph, and rendered asset in the app. Brand palette (coral / ink / paper / mustard / olive) defined once, imported by `client.py` and `history_window.py`.
- **PIL-rendered brand mark** (Φ-in-circle). The widget coin, history-window title-bar mark, settings-tab mark, and tray icon all use `theme.render_mark_image()` at 4x supersample / LANCZOS downsample. Crisp anti-aliasing at every size; no more Tk Canvas oval pixelation.
- **Custom glyph system**. Hand-drawn vector icons in PIL: transcripts, dictionary, pending, settings, search, close, copy, arrow_right, plus, sparkle, trash, and a standalone phi. Tab labels in the history window and inline action icons all use these instead of inconsistent Unicode characters / OS-rendered emoji.
- **Multi-resolution `cait.ico`**. Generated on first launch by `theme.ensure_brand_ico()` into `assets/cait.ico`. Embeds 16/32/48/64/128/256 px renders so Windows picks the right one for taskbar, Alt-Tab, file explorer, and title bar.
- **Waveform style picker** (`Waveform ▸` cascade in the right-click menu). Six visual styles: filled wave, classic bars, mirrored bars (default), dots, oscilloscope, blocks. Selection persists to `config.json` as `waveform_style`. Each style is a `_draw_*` method on `StatusWidget`.
- **Brand-styled right-click menu**. Every `tk.Menu` in the widget is now `_styled_menu()` with INK background, PAPER text, CORAL hover. Consistent with the rest of the app instead of Windows-default light gray.
- **"Cait. whisper" brand lockup**. `theme.brand_lockup()` helper composes bold "Cait" + coral italic period + italic "whisper" as a packed Frame. Applied to: hover card title strip, history window title bar, OS window title bar.
- **Settings tab in the history window** has a coral glyph next to each tab label (transcripts / dictionary / pending / settings) and the brand lockup at the top.
- **`docs/for-testers.md`** - one-page brief written for a non-technical tester.
- **`docs/design-system.md`** and **`docs/providers.md`** - extracted design tokens and LLM provider setup into dedicated docs.

### Changed
- **Resting coin is now quiet** (INK_MUTE warm gray on dark INK coin). The brand mark only "lights up" coral on activity: startup ready toast, COMMAND mode, one-shot armed, correction watch.
- **Recording strip dimensions**: 196×36 → 240×40. More horizontal room, more vertical breathing room, cleaner button alignment.
- **Recording strip buttons** are now PIL-rendered glyphs (close / phi) instead of Tk text labels. Same widget type, same rendering pipeline -> automatic optical alignment. Hover state swaps the PhotoImage instead of changing fg color.
- **Standardized border**: every container outline is now `theme.INK_MUTE` (warm gray) at `theme.BORDER_MED` (2px) for floating chrome, `theme.BORDER_THIN` (1px) for inline dividers. Recording strip border was coral per-state; now consistently gray since the waveform color already signals state.
- **Widget no longer relies on `-transparentcolor`**. That Windows API was unreliable across display drivers / wide-gamut monitors / color profiles - magenta pixels leaked through as visible pink corners on affected machines. The widget is now a small dark INK badge with DWM-rounded corners (squircle on Win11). The PIL image's own alpha channel handles the inside-coin transparency.
- **Widget hidden from taskbar / Alt-Tab** via `WS_EX_TOOLWINDOW`. Floating utility surface, not an app entry alongside Word and Chrome.
- **History window** is wider (540 → 640 px) to accommodate the four tabs with their new coral glyphs.
- **Window title bar** says "Cait. whisper" instead of "Cait" so the taskbar / Alt-Tab match the wordmark.

### Fixed
- **Cross-monitor cursor-follow regression**. `_user_placed=True` was sticky once set, silently disabling follow forever for anyone who had a saved widget position. New rule: same monitor as before -> respect placement. Different physical monitor -> follow, clear `_user_placed`.
- **Idle-unload + start-recording race**. The supervisor would drop `_asr_model = None` after 60s idle; the next `_start_recording` check treated this identically to "still loading" and refused to start. Replaced `is None` checks with `_last_asr_use_time > 0` to distinguish loaded-then-unloaded from never-loaded.
- **Two-pass silently disabled after idle** for the same reason in the trigger gate.
- **`CaitKatKatKat...` intra-word hallucination**. Word-level loop guard missed single-token loops with no spaces. Added regex `(.{2,8}?)\1{4,}` to detect and strip intra-word repetition while keeping the legitimate prefix.
- **Trailing "Thank you." hallucination**. Added trailing-phrase strip list with a min-words guard.
- **`no_speech_prob` filter was too aggressive at 0.7**. Bumped to 0.85 and added a safety net to never return empty if Whisper produced segments.
- **WDM-KS input devices** filtered out of the mic picker (caused `paInvalidDevice` errors).
- **Mic startup fatal failure** if the configured device disappeared between sessions. Falls back to system default with a log warning instead of refusing to launch.
- **Z.AI test connection "no response" generic error**. `test_connection()` now returns the actual exception type and message.

### Repo organization
- `cait.ico` moved to `assets/cait.ico` (auto-generated if missing).
- `ECONOMY.md` and `rewards.json` moved to `docs/economy/`.
- `preview/` (dev-only render output) added to `.gitignore`.
- README hero rewritten as 3-step install for non-technical users.
- `docs/for-testers.md` added for outside testers.

### Backward compatibility
- v2.4 `config.json` files load unchanged. New keys (`waveform_style`, `llm_profiles`, etc.) default to safe values if missing.
- The `appearance.idle_size`/`active_alpha`/etc. keys from v2.4 are still respected.
- The legacy `ollama_model` flat key still falls back when no `llm_profiles` is set.

---

## [2.4.0] - Unreleased (pending UAT sign-off)

### Changed (breaking)
- **Retroactive capture hotkey**: `Ctrl + Win + B` -> `Shift + Alt + R`. The previous combo conflicted with Intel graphics drivers and Lenovo Vantage on some systems. Shift+Alt+letter combos have no Windows global reservations.
- **Mode switching**: new hotkey `Shift + Alt + M` toggles PURE / COMMAND without opening the right-click menu.

### Added
- **`summarize_screen` and `answer_from_screen` commands** (v2.3 follow-up). Say "summarize what you see" or "explain what you see" in COMMAND mode with Screen Context ON and cait-whisper OCRs the region near your cursor, sends the text to Ollama, and pastes the summary/explanation. Closes the gap in v2.3 where the OCR context was captured but nothing actually used it.
- **Dev Logs toggle** (config key `dev_logs`, menu item, log level switches between INFO and DEBUG). When ON, verbose traces log every correction-watch decision, clipboard probe, classifier step, similarity check, and OCR call. Essential for diagnosing auto-dictionary issues.
- **Hover status card** on the widget. Mouse over the dot and a small panel fades in showing engine, mode, and every feature's state. Move away and it disappears. Much better discoverability than the right-click menu alone.
- **Amber pulse** when correction watch is armed. The dot now alternates between two amber shades every ~600ms instead of a static color, so peripheral vision catches it.
- **Clearer mode indicator**: filled dot `●` for PURE, hollow ring `◎` for COMMAND, with brighter blue when COMMAND is active.
- **View Log File** menu item opens `cait-whisper.log` in the user's default text handler.
- **Full user documentation** in `docs/`: installation, getting-started, features, hotkeys, troubleshooting, faq, UAT.

### Fixed
- **COMMAND mode was slow between commands** because `context.get_field_context()` used pywinauto's `descendants()` which walks the entire UI tree. Replaced with `get_focus()` which is O(1). Added a 250ms hard timeout wrapper so even a pathological UI can't block the pipeline.

### Changed (non-breaking)
- **`setup.bat`** now uses `requirements.txt` (picks up new deps like `pywinauto` and `rapidocr-onnxruntime` automatically), offers to install Python via winget if missing, and offers to install Ollama via winget if the user opts in.

### Technical notes
- Dev-mode log traces are `log.debug()` calls, so they incur zero overhead when dev_logs is OFF.
- The hover card is a Tkinter Toplevel that's destroyed on leave. No persistent memory footprint.
- The amber pulse uses `root.after()` scheduling, cancellable when state changes. No thread spawned.

---

## [2.5.0] - Unreleased (pending UAT sign-off)

Headline: cait-whisper is no longer locked to local Ollama. Point it at any OpenAI-compatible endpoint (Z.AI, Groq, Together, OpenAI, DeepSeek, self-hosted vLLM, Tailscale Ollama) and LLM-dependent features run as fast as the network allows. Plus a Settings tab so users never have to hand-edit `config.json`.

### Added
- **Re-transcribe last** (`Shift+Alt+T` and right-click menu cascade). The most recent recording's raw audio is cached after every transcription. When ASR loops or produces garbage, hit Shift+Alt+T to retry with the current engine, or right-click → "Re-transcribe last ▸" to pick a different model (Moonshine → Whisper, etc.) without re-speaking. Memory cost ~32 KB per second of recorded audio.
- **Microphone picker** in the right-click menu (`Microphone ▸`). Lists available input devices, lets the user hot-swap without restarting or changing Windows defaults. Filters out unreliable WDM-KS-only entries to prevent paInvalidDevice errors. Saves to `input_device` config key. Falls back to system default if the saved device disappears.
- **Intra-word hallucination strip**. Single-token loops like "CaitKatKatKat..." (no spaces) now get stripped to the legitimate prefix instead of pasting hundreds of garbage characters. Complements the v2.4 word-level loop guard.
- **Online LLM providers**. New `llm_provider` config key with two values: `local_ollama` (default, identical to v2.4 behavior) and `openai_compatible` (any provider that speaks the OpenAI chat API). Configurable via the new Settings tab or by editing `config.json`. Covers Z.AI, Groq, Together, OpenAI, DeepSeek, self-hosted vLLM, and Tailscale-reachable Ollama-over-HTTPS.
- **Settings tab with saved provider profiles**. New 4th tab in the History & Dictionary window. Save as many named profiles as you want (Z.AI fast, Groq Llama 70B, local Ollama, your Tailscale-reachable server, etc.). Each profile keeps its own Base URL, model, and API key. One profile is ACTIVE at a time; switching is a single click and does NOT require re-entering keys. "Add from preset" dropdown pre-fills endpoints for Local Ollama, Z.AI, Groq, OpenAI, Together, DeepSeek, and Custom. Per-profile "Test connection" button pings with a short prompt and reports OK / failure inline. Read-only display of the current ASR engine and feature toggles for at-a-glance status. Full backward compatibility: v2.4 and v2.5.0-beta configs with the old flat `llm_provider`/`llm_base_url` keys are read on first load and migrated into a profile the first time you save.
- **`llm_provider.py`** - new module providing a single `llm_call()` dispatch helper. Replaces direct `ollama.chat()` calls at all 3 LLM call sites in the codebase.
- **`config_io.py`** - new shared helpers for atomic config read/write and secret-key redaction. Used by both the main client and `history_window.py`.
- **Per-Monitor V2 DPI awareness**. Fixes hover card and widget rendering on multi-monitor setups with mixed DPI scaling.
- **API key log redaction**. Secret-like config keys (`api_key`, `token`, etc.) are replaced with `*** (set, N chars)` in log output. The actual key never appears in `cait-whisper.log`.

### Fixed
- **Multi-monitor hover card mispositioning** when running on a secondary monitor with different DPI from the primary. Per-Monitor V2 awareness combined with the v2.4 virtual-screen positioning logic now renders the card correctly anywhere.
- **Saved widget position bounds check**. Positions saved under v2.4 (DPI-unaware coordinates) could land outside the virtual screen after upgrade. v2.5 validates against virtual-screen bounds and falls back to auto-anchor if the saved coords are off-screen.
- **`_toggle_llm` magic-number `entryconfig(6, ...)`**. Removed; menu now rebuilds via `_rebuild_menu` so adding/removing menu items above LLM Cleanup doesn't poison a different entry.
- **Local Ollama no longer auto-starts** when LLM Cleanup is enabled if the configured provider is `openai_compatible`. Previously cait-whisper spun up an idle Ollama subprocess that never received a call.

### Changed
- `requirements.txt` adds `openai>=1.57`. Local-only users can comment out the line to skip the install.
- `config.example.json` adds `llm_provider`, `llm_base_url`, `llm_api_key`, `llm_model` keys (all optional, defaulted, backward-compatible with v2.4 configs).
- `_save_config_keys` now redacts secret-like values in log output.

### Backward compatibility
- v2.4 `config.json` files continue working without modification. Missing `llm_provider` key defaults to `local_ollama` (no behavior change).
- `ollama_model` config key is preserved as a fallback when `llm_model` is unset.
- All v2.4 features (auto-dict, one-shot commands, hover card, retroactive capture, screen context, two-pass) work unchanged.

### Deferred to v2.5.1 (next release)
- **Timezone tab** in the productivity panel
- **Tier 1 voice commands** (text editing: select all, copy, paste, bold, save, etc.)
- **Tier 3 meta commands** (cancel, open history, quit, etc.)
- **Commands reference tab** for discoverability

### Deferred to v2.6+
- **Remote ASR endpoint** (a `_RemoteWhisperEngine` class for the hot path)
- **Trigger word mode** ("Nova, [command]" without a hotkey)
- **Multi-lingual dictation**

---

## [2.4.0] - 2026-04-18

### Fixed (critical)
- **Auto-dictionary was permanently broken** after any silent exception in the Enter handler. The `_correction_debounce` flag set at handler entry was only reset on specific success paths; any uncaught error or unusual code path left it stuck at True, blocking every subsequent correction for the rest of the session. Wrapped the handler body in try/finally so debounce ALWAYS resets. Also reset on arming.
- **"new paragraph" voice command never fired** because the spoken-punctuation rule `"new paragraph" → "\n\n"` ran before the classifier and converted the command phrase to empty string. Added an early-path classifier that tries regex-based command matching on the raw ASR output BEFORE spoken-punctuation touches it.
- **pywinauto `get_focus()` raised on every COMMAND-mode invocation** because that method doesn't exist on the Desktop class. Reverted to descendants() walk wrapped in the 250 ms timeout so slow UIs don't block the pipeline.
- **Hover card mispositioned on multi-monitor setups** - used `winfo_screenwidth()` which returns primary-monitor-only dimensions, so on secondary monitors the card got clamped back to the primary edge. Switched to `GetSystemMetrics(SM_XVIRTUALSCREEN)` etc. for virtual screen bounds across all monitors.
- **Widget snapped back to default position** after every manual drag because the 500 ms heartbeat re-anchored to the cursor's monitor's bottom-right. Added `_user_placed` flag; heartbeat skips auto-anchor once set. Drag position now persists to `config.json` and survives restart.
- **Whisper initial-prompt-induced hallucination loops** when the personal dictionary got large enough that joining all values produced a long prompt. Capped to 12 words.
- **Hallucination guard stripping vs discarding** - the v2.3.1 guard threw away the entire transcription if any part contained a loop. Now strips just the repeated region and preserves the legitimate prefix/suffix (e.g. 97 real words kept even when "Thank you." repeats 50 times at the end).

### Added
- **`Shift+Alt+C` one-shot COMMAND mode**: tap to record, tap to execute, auto-reverts to PURE. Replaces the old `Shift+Alt+M` sticky toggle as the primary command flow. Sticky toggle remains available in the right-click menu for power users.
- **`Shift+Alt+R` retroactive capture** (renamed from the conflict-prone `Ctrl+Win+B`).
- **Pending-correction toast**: every time the auto-dictionary spots a candidate but hasn't promoted yet, a small amber toast on the widget shows `📝 'kate' → 'cait' (1/2 · 1 more)`. The pending queue is no longer invisible.
- **Hover status card** on the widget. Mouse-over the dot and a panel fades in showing engine, mode, and every feature's state. Hides instantly on cursor leave.
- **Amber pulse** when correction watch is armed (was a static color, now alternates two shades every 600 ms so peripheral vision catches it).
- **Distinct glyphs for modes**: filled dot `●` for PURE, hollow ring `◎` for COMMAND. Brighter blue shade when one-shot is armed.
- **"View Log File" menu item** opens `cait-whisper.log` in the default text handler.
- **"Dev Logs: ON/OFF" toggle** flips log level between INFO and DEBUG. Verbose traces in correction-watch, clipboard probe, classifier, similarity check, OCR paths.
- **Model-switch sound**: quick audible confirmation when the ASR model finishes swapping.
- **`summarize_screen` and `answer_from_screen` commands** closing the v2.3 screen-context gap. Say "summarize what you see" or "explain what you see" with Screen Context ON.
- **`setup.bat` offers Python and Ollama via winget** if not already installed.
- **`docs/` folder** with installation, getting-started, features, hotkeys, troubleshooting, faq, UAT.

### Changed
- `config.json` gains `dev_logs`, `widget_position` keys. Existing configs keep working.
- Right-click menu label "Mode: PURE/COMMAND" → "Sticky COMMAND mode: ON/OFF" (clarifies that this is the persistent toggle, not the one-shot).

### Still not fixed (rolled to v2.5)
- LLM features (selection rewrite, screen-context commands) still require local Ollama and feel slow on modest hardware. v2.5 adds online provider support (OpenAI-compatible, covers Z.AI / Groq / Together / DeepSeek / self-hosted vLLM / Tailscale Ollama).
- Multi-monitor hover card positioning deferred to v2.5 UAT (tester didn't have a second monitor during this round).

---

## [2.3.1] - 2026-04-16

### Fixed
- **Command classifier LLM fallback crashed with KeyError** - `COMMAND_PROMPT` contained literal `{"is_command": ...}` JSON which Python's `str.format()` misread as a placeholder. Any utterance that missed the regex fast-path (e.g. "rewrite this formally" without a selection) would trigger the LLM path and raise `KeyError: '"is_command"'`. Escaped the literal braces with `{{` `}}`. Caught during smoke testing before any user hit it in the wild.

### Smoke test coverage
- 34/34 classifier test cases pass (regex fast-path + edge cases + dictation false-positive checks).
- 8/8 two-pass toast-logic cases pass (identical, normalized-equal, minor typo filtered, meaningful diff flagged, empty-safe).
- `context.get_active_window()` verified against real foreground process.
- `context.capture_screen_region()` + RapidOCR end-to-end verified: ~2 s first-call (ONNX init), subsequent calls fast.
- Known limitation confirmed: `get_field_context()` returns empty for apps that don't expose UI Automation text pattern (e.g. Electron apps). Graceful fallback means selection-based commands simply don't fire, which is the safe default.

---

## [2.3.0] - 2026-04-16

### Added
- **Screen-context capture** - in COMMAND mode, cait-whisper can OCR the region around the cursor and feed the text to the LLM classifier as context. Enables utterances like "write an approving comment but ask about test coverage" while looking at a PR.
- **"Screen Context: ON/OFF" toggle** - right-click menu item. Default OFF, explicit opt-in.
- **`use_screen_context: false`** config key.
- **`context.capture_screen_context()`** - one-shot helper: cursor position -> screen region -> OCR text. Uses `PIL.ImageGrab` (already installed) and `rapidocr-onnxruntime` (new optional dependency).
- **`context.get_cursor_pos()`**, **`context.capture_screen_region()`**, **`context.ocr_image()`** - lower-level helpers.

### Technical notes
- RapidOCR is imported lazily (cached after first use). If `rapidocr-onnxruntime` isn't installed, screen context silently degrades to empty-string and the LLM classifier runs normally.
- OCR latency is typically 30-80 ms on CPU, negligible next to the LLM call it augments.
- Screen context is only captured when COMMAND mode is ON and the user has enabled the toggle. PURE mode is completely unaffected.
- Maximum captured text is clipped to 1500 chars to preserve prompt budget on small local models.

### Privacy
- All OCR runs locally via ONNX. No images, no screenshots, no text leaves the machine.
- Captured region is centered on the cursor (700x400 default) so background apps aren't scraped.

---

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
