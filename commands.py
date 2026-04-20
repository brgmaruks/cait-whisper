"""Voice command classification and execution for cait-whisper COMMAND mode.

In PURE mode (default) this module is never invoked. In COMMAND mode,
every transcription is routed through `classify()` which returns either:

  - a Command to execute (regex fast-path or high-confidence LLM result)
  - None, meaning "this is dictation, paste it normally"

The classifier prefers the regex fast-path for zero latency on common
commands like "new paragraph" and "delete that sentence". Only ambiguous
utterances fall back to the local LLM, adding ~300ms when they do.

Commands are executed via `execute()`. Text-editing commands translate
to keyboard events (Ctrl+Z, Backspace, etc.). Selection commands send
the selection through a rewrite prompt and paste the result back.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger("cait-whisper")

# ── Command identifiers ───────────────────────────────────────────────────
# Keep these as plain strings so they serialize cleanly to/from LLM JSON.

CMD_NEW_PARAGRAPH   = "new_paragraph"
CMD_NEW_LINE        = "new_line"
CMD_DELETE_SENTENCE = "delete_sentence"
CMD_DELETE_WORD     = "delete_word"
CMD_CAPITALIZE_LAST = "capitalize_last"
CMD_CLEAR_FIELD     = "clear_field"
CMD_UNDO            = "undo"
CMD_RETRY           = "retry"

# Selection-based commands (require has_selection=True)
CMD_REWRITE_FORMAL  = "rewrite_formal"
CMD_REWRITE_CASUAL  = "rewrite_casual"
CMD_REWRITE_SHORTER = "rewrite_shorter"
CMD_REWRITE_LONGER  = "rewrite_longer"
CMD_SUMMARIZE       = "summarize_selection"

# Screen-context commands (v2.4, require screen OCR context)
CMD_SUMMARIZE_SCREEN = "summarize_screen"
CMD_ANSWER_SCREEN    = "answer_from_screen"

# ── Fast-path regex table ─────────────────────────────────────────────────
# Ordered list of (compiled pattern, command_id). First match wins.
# Patterns are anchored loosely (\b) so they fire on natural speech
# ("okay, new paragraph please" still triggers).

_FAST_COMMANDS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^\s*new\s+paragraph\s*\.?\s*$", re.I), CMD_NEW_PARAGRAPH),
    (re.compile(r"^\s*new\s+line\s*\.?\s*$", re.I), CMD_NEW_LINE),
    (re.compile(r"^\s*delete\s+(that|the\s+last\s+sentence)\s*\.?\s*$", re.I), CMD_DELETE_SENTENCE),
    (re.compile(r"^\s*delete\s+(the\s+)?last\s+word\s*\.?\s*$", re.I), CMD_DELETE_WORD),
    (re.compile(r"^\s*capitalize\s+(that|the\s+last\s+word)\s*\.?\s*$", re.I), CMD_CAPITALIZE_LAST),
    (re.compile(r"^\s*clear\s+(the\s+)?(text|field)\s*\.?\s*$", re.I), CMD_CLEAR_FIELD),
    (re.compile(r"^\s*undo\s+that\s*\.?\s*$", re.I), CMD_UNDO),
    (re.compile(r"^\s*try\s+again\s*\.?\s*$", re.I), CMD_RETRY),
]

# Selection commands (only relevant when text is selected). Also regex-matchable
# because natural phrasings are predictable.
_SELECTION_COMMANDS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(make\s+this|rewrite\s+this)\s+(more\s+)?formal\b", re.I), CMD_REWRITE_FORMAL),
    (re.compile(r"\b(make\s+this|rewrite\s+this)\s+(more\s+)?casual\b", re.I), CMD_REWRITE_CASUAL),
    (re.compile(r"\b(make\s+this|rewrite\s+this)\s+shorter\b", re.I), CMD_REWRITE_SHORTER),
    (re.compile(r"\bshorten\s+(this|that)\b", re.I), CMD_REWRITE_SHORTER),
    (re.compile(r"\b(make\s+this|rewrite\s+this)\s+longer\b", re.I), CMD_REWRITE_LONGER),
    (re.compile(r"\bexpand\s+(this|that|on\s+this)\b", re.I), CMD_REWRITE_LONGER),
    (re.compile(r"\bsummarize\s+(this|that)\b", re.I), CMD_SUMMARIZE),
]

# Screen-context commands (only relevant when screen_context is non-empty).
# Triggered when the user refers to "what you see / this page / the screen".
_SCREEN_COMMANDS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bsummariz(e|ing)\s+(what\s+you\s+see|this\s+page|the\s+screen|this\s+screen)\b", re.I), CMD_SUMMARIZE_SCREEN),
    (re.compile(r"\bwhat'?s\s+on\s+(the\s+|my\s+)?screen\b", re.I), CMD_SUMMARIZE_SCREEN),
    (re.compile(r"\bexplain\s+(what\s+you\s+see|this\s+page|the\s+screen|this\s+screen)\b", re.I), CMD_ANSWER_SCREEN),
]


@dataclass
class Command:
    """A classified command ready for execution."""
    type: str
    confidence: float
    args: str = ""                # any free-form argument (used by LLM path)
    source: str = "regex"         # "regex" or "llm"
    raw_text: str = ""            # original utterance (for logging)


# ── LLM fallback prompt ───────────────────────────────────────────────────
# Strict JSON output keeps parsing deterministic.

COMMAND_PROMPT = """You classify voice utterances from a dictation app as either a COMMAND (to execute) or DICTATION (text to type verbatim).

Reply ONLY with JSON matching this schema:
{{"is_command": true|false, "type": "<command_id>"|"", "confidence": 0.0-1.0, "reasoning": "<brief>"}}

Known command IDs:
- new_paragraph, new_line
- delete_sentence, delete_word
- capitalize_last, clear_field, undo, retry
- rewrite_formal, rewrite_casual, rewrite_shorter, rewrite_longer
- summarize_selection

Rules:
- If unsure, prefer DICTATION (is_command=false). The default is safety.
- Only output is_command=true when confidence >= 0.85.
- Utterances longer than ~8 words are almost always dictation.
- Selection-based commands (rewrite_*, summarize_selection) require a selection; if unclear, set confidence lower.

Selection present: {has_selection}
{screen_context_block}
Utterance: {utterance}"""


def _llm_classify(utterance: str, has_selection: bool, screen_context: str = "") -> Optional[Command]:
    """Call Ollama to classify the utterance. Returns None on any failure.

    Optional `screen_context` (OCR text from around the cursor, v2.3) is
    appended to the prompt so the model can reason about what the user is
    looking at. Empty string disables screen-context augmentation.
    """
    try:
        # Imported lazily so cait-whisper still imports if ollama isn't installed
        import ollama  # type: ignore
    except Exception:
        return None

    try:
        # Read model name from a module-level config that client.py will set
        from client import OLLAMA_MODEL  # type: ignore
    except Exception:
        OLLAMA_MODEL = "llama3.2:3b"

    # Build the optional screen-context block. Kept small to avoid blowing
    # the prompt budget on low-end models.
    if screen_context.strip():
        screen_block = (
            "SCREEN CONTEXT (what the user is looking at, via OCR):\n"
            f"{screen_context.strip()[:1500]}\n"
        )
    else:
        screen_block = ""

    prompt = COMMAND_PROMPT.format(
        has_selection="yes" if has_selection else "no",
        screen_context_block=screen_block,
        utterance=utterance.strip(),
    )
    try:
        t0 = time.perf_counter()
        resp = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1, "num_predict": 128},
        )
        elapsed = time.perf_counter() - t0
        content = resp["message"]["content"].strip()
        # Some models wrap JSON in code fences; strip them
        if content.startswith("```"):
            content = content.strip("`").lstrip("json").strip()
        data = json.loads(content)
        log.info(f"[Commands] LLM classified in {elapsed:.2f}s: {data}")
        if not data.get("is_command"):
            return None
        return Command(
            type=str(data.get("type", "")),
            confidence=float(data.get("confidence", 0.0)),
            args="",
            source="llm",
            raw_text=utterance,
        )
    except Exception as e:
        log.warning(f"[Commands] LLM classify failed: {e}")
        return None


# ── Public entry point: classify() ────────────────────────────────────────

_CONFIDENCE_THRESHOLD = 0.7


def classify(utterance: str, has_selection: bool = False, screen_context: str = "") -> Optional[Command]:
    """Return a Command if `utterance` is a voice command, else None.

    Algorithm:
      1. If selection exists, check selection-regex table first.
      2. Try general regex fast-path.
      3. Call LLM fallback for ambiguous utterances (short, no regex match).
         If `screen_context` is provided (v2.3), it augments the LLM prompt
         with OCR text from around the cursor.
      4. Apply confidence threshold.
    """
    text = utterance.strip()
    if not text:
        return None

    # Word-count sanity: commands are usually short (<=8 words).
    # Longer utterances skip the LLM path to avoid slow false positives.
    word_count = len(text.split())
    too_long_for_command = word_count > 12

    # 1. Selection regex first (only if something is selected)
    if has_selection:
        for pat, cmd_id in _SELECTION_COMMANDS:
            if pat.search(text):
                log.info(f"[Commands] regex match (selection): {cmd_id} <- {text!r}")
                return Command(type=cmd_id, confidence=0.95, source="regex", raw_text=utterance)

    # 2. Screen-context regex (only if OCR actually produced something)
    if screen_context.strip():
        for pat, cmd_id in _SCREEN_COMMANDS:
            if pat.search(text):
                log.info(f"[Commands] regex match (screen): {cmd_id} <- {text!r}")
                # Args carry the OCR text so the executor can use it
                return Command(type=cmd_id, confidence=0.95, args=screen_context,
                               source="regex", raw_text=utterance)

    # 3. General regex fast-path
    for pat, cmd_id in _FAST_COMMANDS:
        if pat.match(text):
            log.info(f"[Commands] regex match: {cmd_id} <- {text!r}")
            return Command(type=cmd_id, confidence=0.95, source="regex", raw_text=utterance)

    # 3. LLM fallback for ambiguous short utterances
    if too_long_for_command:
        return None
    cmd = _llm_classify(text, has_selection, screen_context=screen_context)
    if cmd is None:
        return None
    if cmd.confidence < _CONFIDENCE_THRESHOLD:
        log.info(f"[Commands] LLM below threshold ({cmd.confidence:.2f}) - treating as dictation")
        return None
    return cmd


# ── Execution ─────────────────────────────────────────────────────────────

# Keyboard ops delegated to the caller's `keyboard` module so we don't
# force a top-level dependency here. Caller passes a reference in `kb`.

# Rewrite prompts for selection commands
_REWRITE_PROMPTS = {
    CMD_REWRITE_FORMAL:  "Rewrite the following text to be more formal and professional while preserving the meaning exactly. Output only the rewritten text:\n\n{text}",
    CMD_REWRITE_CASUAL:  "Rewrite the following text to be more casual and conversational while preserving the meaning. Output only the rewritten text:\n\n{text}",
    CMD_REWRITE_SHORTER: "Rewrite the following text to be significantly shorter while preserving the key meaning. Output only the rewritten text:\n\n{text}",
    CMD_REWRITE_LONGER:  "Expand the following text with more detail while preserving the meaning and tone. Output only the expanded text:\n\n{text}",
    CMD_SUMMARIZE:       "Summarize the following text in one or two sentences. Output only the summary:\n\n{text}",
    CMD_SUMMARIZE_SCREEN: "Summarize what is shown on the user's screen, based on the OCR text below. Be brief, one or two sentences. Output only the summary, no preamble:\n\nScreen text:\n{text}",
    CMD_ANSWER_SCREEN:    "Explain clearly and briefly what is shown on the user's screen, based on the OCR text below. One short paragraph max. Output only the explanation, no preamble:\n\nScreen text:\n{text}",
}


def _llm_rewrite(text: str, command_type: str) -> Optional[str]:
    """Run a rewrite/summarize prompt through Ollama. None on failure."""
    try:
        import ollama  # type: ignore
    except Exception:
        return None
    try:
        from client import OLLAMA_MODEL  # type: ignore
    except Exception:
        OLLAMA_MODEL = "llama3.2:3b"

    template = _REWRITE_PROMPTS.get(command_type)
    if not template:
        return None
    try:
        resp = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": template.format(text=text)}],
            options={"temperature": 0.3, "num_predict": 512},
        )
        return resp["message"]["content"].strip()
    except Exception as e:
        log.warning(f"[Commands] rewrite via LLM failed: {e}")
        return None


def execute(cmd: Command, selection_text: str = "", kb=None, paste_fn=None) -> bool:
    """Execute a command. Returns True on success.

    Parameters:
      cmd: the Command to execute.
      selection_text: text currently selected in the focused field (for rewrite/summarize).
      kb: the `keyboard` module (caller supplies to avoid hard dep).
      paste_fn: callable(str) -> None that copies + pastes text (caller supplies).
    """
    t = cmd.type
    log.info(f"[Commands] executing {t} (confidence={cmd.confidence:.2f}, source={cmd.source})")

    if kb is None:
        log.warning("[Commands] no keyboard module supplied; cannot execute")
        return False

    try:
        # ── Text-editing ops ──────────────────────────────────────────
        if t == CMD_NEW_PARAGRAPH:
            kb.send("enter")
            kb.send("enter")
            return True
        if t == CMD_NEW_LINE:
            kb.send("enter")
            return True
        if t == CMD_DELETE_SENTENCE:
            # Select to beginning of sentence and delete. Rough heuristic:
            # hold Shift+Home to select from cursor to line start.
            kb.send("shift+home")
            kb.send("delete")
            return True
        if t == CMD_DELETE_WORD:
            kb.send("ctrl+backspace")
            return True
        if t == CMD_CAPITALIZE_LAST:
            # Select last word (Ctrl+Shift+Left), capture it, transform, paste
            # Simpler: select last word, retype capitalized via clipboard
            kb.send("ctrl+shift+left")
            time.sleep(0.05)
            import pyperclip  # type: ignore
            saved = pyperclip.paste()
            kb.send("ctrl+c")
            time.sleep(0.08)
            word = pyperclip.paste().strip()
            if word:
                capitalized = word[0].upper() + word[1:]
                pyperclip.copy(capitalized)
                time.sleep(0.05)
                kb.send("ctrl+v")
            pyperclip.copy(saved)
            return True
        if t == CMD_CLEAR_FIELD:
            kb.send("ctrl+a")
            kb.send("delete")
            return True
        if t == CMD_UNDO:
            kb.send("ctrl+z")
            return True
        if t == CMD_RETRY:
            # Retry is handled by the caller - it should re-run last transcription
            log.info("[Commands] retry is a caller-level action; returning True")
            return True

        # ── Screen-context ops (input is OCR text from cmd.args) ──────
        if t in (CMD_SUMMARIZE_SCREEN, CMD_ANSWER_SCREEN):
            source_text = cmd.args.strip() if cmd.args else ""
            if not source_text:
                log.warning(f"[Commands] {t} needs screen OCR context but got nothing")
                return False
            new_text = _llm_rewrite(source_text, t)
            if not new_text:
                return False
            if paste_fn:
                paste_fn(new_text)
            else:
                import pyperclip  # type: ignore
                pyperclip.copy(new_text)
                time.sleep(0.05)
                kb.send("ctrl+v")
            return True

        # ── Selection-based ops (input is highlighted text) ──────────
        if t in _REWRITE_PROMPTS:
            if not selection_text.strip():
                log.warning(f"[Commands] {t} requires a selection but none provided")
                return False
            new_text = _llm_rewrite(selection_text, t)
            if not new_text:
                return False
            if paste_fn:
                paste_fn(new_text)
            else:
                import pyperclip  # type: ignore
                pyperclip.copy(new_text)
                time.sleep(0.05)
                kb.send("ctrl+v")
            return True

        log.warning(f"[Commands] unknown command type: {t}")
        return False
    except Exception as e:
        log.error(f"[Commands] execute failed for {t}: {e}")
        return False


# ── Self-test ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    tests = [
        ("new paragraph", False),
        ("new line", False),
        ("delete the last sentence", False),
        ("hello world this is just dictation", False),
        ("make this more formal", True),
        ("shorten this", True),
        ("summarize this please", True),
    ]
    for utt, sel in tests:
        cmd = classify(utt, has_selection=sel)
        print(f"{utt!r:50} selection={sel} -> {cmd}")
