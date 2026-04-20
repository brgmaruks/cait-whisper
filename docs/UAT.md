# User Acceptance Testing (UAT)

Structured walkthrough for every release. Each section tests one feature or fix. Run top to bottom. If anything fails, note which group and item number, and paste the relevant log lines.

**Keep this document up to date**: after every release, append new tests for new features. Old tests stay in as regression checks.

## Pre-flight

- [ ] Run `pip install -r requirements.txt` in the project venv (picks up `pywinauto` and `rapidocr-onnxruntime`).
- [ ] Verify Ollama is installed: `ollama --version` in a terminal.
- [ ] Pull a model if you haven't: `ollama pull llama3.2:3b`.
- [ ] Open a second terminal and tail the log: `Get-Content cait-whisper.log -Wait -Tail 20` (PowerShell).
- [ ] **Turn on Dev Logs** before starting: launch the app, right-click the widget, click "Dev Logs: OFF" to flip it ON. Verbose traces make every failure diagnosable.
- [ ] Launch `start.bat`. Accept UAC.

---

## Group A: PURE mode regression check

1. [ ] Widget dot appears bottom-right, filled circle `●`, gray.
2. [ ] Log shows `startup: ASR model ready` then a green flash on the dot.
3. [ ] Open Notepad, click into it.
4. [ ] Hold `Ctrl + Win`, say "hello world", release.
5. [ ] **Expected**: "Hello world." or similar appears in Notepad within ~1 second (Moonshine).
6. [ ] Log shows `Pasted (X.XXs total)`.

**If this fails, stop. Do not continue. Report to me.**

## Group B: Hands-free mode

1. [ ] Click into Notepad.
2. [ ] Press `Ctrl + Win + Space`. Widget expands, shows ✕ and ⏺ buttons.
3. [ ] Speak two sentences with a pause between them.
4. [ ] Press `Ctrl + Win + Space` again to stop.
5. [ ] **Expected**: Both sentences paste.

## Group C: Mode switching (new hotkey)

1. [ ] Hover cursor over the dot for ~1 second.
2. [ ] **Expected**: Hover card appears above-left of dot, showing Engine, Mode: PURE, all feature states.
3. [ ] Move cursor away. Card disappears after ~250ms.
4. [ ] Right-click the dot. Verify the menu now contains:
    - Mode: PURE
    - Two-Pass: ON (or OFF depending on config)
    - Screen Context: OFF
    - Dev Logs: ON
    - View Log File
5. [ ] Close the menu by clicking elsewhere.
6. [ ] Press `Shift + Alt + C`.
7. [ ] **Expected**: Dot changes to hollow ring `◎` with brighter blue color.
8. [ ] Log shows `Mode switched to COMMAND`.
9. [ ] Hover card confirms "Mode: COMMAND".
10. [ ] Press `Shift + Alt + C` again. Dot returns to filled gray `●`.
11. [ ] Log shows `Mode switched to PURE`.

## Group D: Regex voice commands (no Ollama needed)

Switch to COMMAND mode (`Shift + Alt + C`). Click into Notepad. Type: `the quick brown fox jumps over the lazy dog`

For each:

| # | Utterance | Expected result | Expected log line |
|---|-----------|-----------------|-------------------|
| 1 | "new paragraph" | Cursor jumps two lines down | `regex match: new_paragraph` |
| 2 | "new line" | One line break inserted | `regex match: new_line` |
| 3 | "delete the last word" | "dog" disappears | `regex match: delete_word` |
| 4 | "capitalize that" | Previous word becomes Capitalized | `regex match: capitalize_last` |
| 5 | "undo that" | Last change reverts (Ctrl+Z) | `regex match: undo` |
| 6 | "clear the field" | Notepad empties | `regex match: clear_field` |

**Notes**:
- [ ] None of these should feel slow. If there's a noticeable delay between speech end and command execution, the field-context capture is timing out. Check log for `[Context] get_field_context timed out`.

## Group E: Dictation in COMMAND mode still pastes

Still in COMMAND mode, click into Notepad. Say: "this is a long sentence that should be dictated normally"

1. [ ] **Expected**: Text pastes verbatim.
2. [ ] Log shows a normal `Pasted` line with no `[Mode=COMMAND] classified as` preceding it, OR shows `classifier error` then falls through.
3. [ ] No command fires. No accidental capitalize, no delete.

## Group F: Selection-based rewriting (requires Ollama)

Make sure Ollama is running: `ollama list` in a terminal should list at least one model.

1. [ ] In Notepad, type: "This is a fairly long and somewhat verbose sentence that could probably be written much more concisely with a bit of effort."
2. [ ] Select the whole sentence with Ctrl+A.
3. [ ] Switch to COMMAND mode if not already (`Shift + Alt + C`).
4. [ ] Say "shorten this".
5. [ ] **Expected**: Within 1-3 seconds the selection gets replaced by a shorter rewrite.
6. [ ] Log shows `[Commands] regex match (selection): rewrite_shorter` then `[Commands] executing rewrite_shorter`.

If this fails:
- [ ] Check log for `[Commands] rewrite via LLM failed`. Usually means Ollama isn't running or the model isn't pulled.
- [ ] Verify `ollama list` shows at least `llama3.2:3b`.

## Group G: Two-pass transcription

1. [ ] Primary engine must be Moonshine. Check right-click menu -> Switch Model -> Moonshine has a ✓.
2. [ ] Watch log at startup for: `[TwoPass] loading background Whisper` then `background Whisper ready in Xs`. Two-pass is armed only after this line appears.
3. [ ] Record a 10-15 second dictation with at least one tricky word (proper noun, technical term, uncommon word).
4. [ ] Paste happens immediately (Moonshine).
5. [ ] Wait 2-5 seconds.
6. [ ] **Expected**: If Whisper produced a different transcription, a blue toast appears on the widget with a preview and the text "Better version available · Shift+Alt+Z".
7. [ ] Press `Shift + Alt + Z`. The improved version should re-paste.
8. [ ] Log shows `[TwoPass] better transcription (ratio=0.XX)` at the decision point.

If the toast never fires even after many attempts, two-pass may be working but the background engine keeps agreeing with Moonshine (both producing the same text). Try a more challenging sentence.

## Group H: Retroactive capture (new hotkey)

1. [ ] Click into Notepad so it has focus.
2. [ ] Speak for ~10 seconds WITHOUT holding any hotkey: "the quick brown fox jumped over the lazy dog and then ran away into the forest where no one could find it ever again"
3. [ ] Press `Shift + Alt + R`.
4. [ ] **Expected**: Within a second or two, the sentence you just said gets transcribed and pasted.
5. [ ] Log shows `[Retro] transcribing last ~N.Ns (M chunks)` then normal paste.

**Negative test**: press `Shift + Alt + R` immediately after launch before speaking anything.
- [ ] Log should show `[Retro] buffer is empty` and nothing gets pasted.

## Group I: Screen context + screen commands (requires Ollama)

1. [ ] Open a webpage or document with visible text.
2. [ ] In COMMAND mode, right-click widget -> "Screen Context: ON".
3. [ ] Position your cursor over meaningful content on the page.
4. [ ] Click into Notepad in a different window/monitor.
5. [ ] Trigger dictation (hold `Ctrl + Win`) and say "summarize what you see".
6. [ ] **Expected**: A one or two sentence summary of what the screen context captured gets pasted into Notepad.
7. [ ] Log shows:
    - `[ScreenContext] captured NNN chars in X.XXs`
    - `[Commands] regex match (screen): summarize_screen`
    - `[Commands] executing summarize_screen`

Known limitations:
- First OCR call is ~2 seconds (model load). Subsequent calls are fast.
- OCR captures a 700x400 box centered on the cursor. If your cursor is far from the content you want summarized, move it first.

## Group J: Auto-dictionary (the debug target)

This is the one we specifically want to debug with dev logs.

1. [ ] Ensure Dev Logs is ON.
2. [ ] Right-click -> Auto-Learn: ON (if not already).
3. [ ] Click into Notepad.
4. [ ] Hold `Ctrl + Win`, say "my name is kate", release.
5. [ ] **Expected**: "My name is Kate." pastes.
6. [ ] **Expected** log line: `[AutoDict] watching for corrections (press Enter to commit)` followed by `[AutoDict] armed with original_text=...`
7. [ ] **Expected**: Widget dot pulses amber (alternating between two shades every ~600ms).
8. [ ] Double-click "Kate" to select just that word. Type "Cait". The text should now read "My name is Cait."
9. [ ] Press Enter.
10. [ ] **Expected** log lines (in order):
    - `[AutoDict] Enter handler fired`
    - `[AutoDict] clipboard read: len=N, matches_original=True`
    - `[AutoDict] clipboard unchanged; probing field via Ctrl+A/Ctrl+C`
    - `[AutoDict] Ctrl+A/Ctrl+C grab: len=N`
    - `[AutoDict] grabbed field content via Ctrl+A/Ctrl+C`
    - `[AutoDict] diff inputs: original='My name is Kate.' corrected='My name is Cait.'` (or similar)
    - `[AutoDict] opcode=replace orig[3:4]=['Kate.'] corr[3:4]=['Cait.']`
    - `[AutoDict] 1 candidate pair(s) before similarity gate`
    - `[AutoDict] similarity check 'kate' vs 'cait' -> True`
    - `[AutoDict] pending key 'kate→cait' now count=1`
    - `[AutoDict] pending: 'kate' → 'cait' (count=1, need 1 more)`
11. [ ] Dot returns to non-pulsing appearance.
12. [ ] Repeat steps 3-9 a second time. On the second Enter, log should show `[AutoDict] PROMOTED to dictionary: 'kate' → 'cait'` and a green toast should flash on the widget.
13. [ ] Hold `Ctrl + Win`, say "my name is kate" one more time.
14. [ ] **Expected**: The paste shows "Cait" instead of "Kate" because the dictionary applied.
15. [ ] Log shows `Dictionary applied: ...`.

**If auto-dict STILL doesn't work, paste the full log output between `[AutoDict] watching` and the last `[AutoDict]` line.** That's our diagnostic trail.

## Group K: View Log menu

1. [ ] Right-click widget -> "View Log File".
2. [ ] **Expected**: `cait-whisper.log` opens in your default text editor.

## Group L: Widget appearance & discoverability

1. [ ] Dot is visible bottom-right of the primary monitor.
2. [ ] In PURE mode: filled circle `●`, gray.
3. [ ] In COMMAND mode: hollow ring `◎`, brighter blue.
4. [ ] Correction watch active: alternates between two amber shades every ~600ms (pulse).
5. [ ] Ready toast: green flash for 2 seconds after model loads.
6. [ ] Two-pass toast: blue panel with preview, auto-dismisses after 4 seconds.
7. [ ] Dict-learned toast: green panel with arrow between words, auto-dismisses.
8. [ ] Hover card: gray background, shows all active feature states.

## Group M: Drag to reposition + survives restart

1. [ ] Click and drag the dot to a new location.
2. [ ] Quit the app (right-click -> Quit).
3. [ ] Relaunch via `start.bat`.
4. [ ] **Expected**: Dot appears at the new location.
5. [ ] Right-click -> "Reset Position" returns it to the default bottom-right.

---

## Known limitations (won't be fixed in v2.4)

- **Selection detection** only works in apps that expose UI Automation's TextPattern. Electron apps, terminals, and password fields report empty selection. Commands silently fall through to dictation.
- **OCR first call** takes ~2 seconds while the ONNX model loads. Subsequent calls are fast.
- **Hotkey customization** via config is not yet exposed. To change a hotkey, edit `client.py` directly.

---

## Reporting results

When done, post a summary:

- Groups passed (e.g. "A through E, G, H pass")
- Groups failed (e.g. "F failed at step 5 because Ollama 403")
- Anything unexpected (weird visuals, delays, missed commands)
- Attach the relevant log snippet for each failure

We fix what's broken, then tag and push.
