"""
cait-whisper — fully local speech-to-text dictation for Windows

Switch engines in config.json:
    "engine": "moonshine"   → Moonshine ONNX  (fastest on CPU, ~400 MB)
    "engine": "whisper"     → faster-whisper  (fallback, more model options)

Hotkeys:
    Ctrl+Win (hold)     → speak → release → transcribe + paste
    Ctrl+Win+Space      → hands-free: talk freely, then Ctrl+Win to paste
"""

import collections
import ctypes
import datetime
import difflib
import json
import logging
import logging.handlers
import math
import os
import random
import re
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import traceback
from pathlib import Path

# ─── Early crash handler ──────────────────────────────────────────────────────
# Runs before logging is configured, so we write directly to the log file
# and show a GUI dialog (no console when launched via pythonw).
_LOG_PATH_EARLY = Path(__file__).parent / "cait-whisper.log"

def _fatal(message: str, exc: Exception = None):
    """Show a GUI error dialog and write to log, then exit."""
    detail = f"{message}\n\n{traceback.format_exc()}" if exc else message
    try:
        with open(_LOG_PATH_EARLY, "a", encoding="utf-8") as f:
            f.write(f"\n[FATAL] {detail}\n")
    except Exception:
        pass
    try:
        _r = tk.Tk()
        _r.withdraw()
        from tkinter import messagebox
        messagebox.showerror("cait-whisper — startup error",
                             f"{message}\n\nPlease run setup.bat, then try again.\n\n"
                             f"Full details in cait-whisper.log")
        _r.destroy()
    except Exception:
        pass
    sys.exit(1)

try:
    from PIL import Image, ImageDraw
except ImportError as e:
    _fatal("Pillow is not installed.", e)

try:
    import keyboard
    import numpy as np
    import pyperclip
    import sounddevice as sd
    import soundfile as sf
except ImportError as e:
    _fatal(f"Missing package: {e}", e)

# ─── Logging — console + rotating log file ────────────────────────────────────
_LOG_PATH = Path(__file__).parent / "cait-whisper.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),                                        # console (visible when run via python, not pythonw)
        logging.handlers.RotatingFileHandler(
            _LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8",
        ),
    ],
)
log = logging.getLogger("cait-whisper")

# ─── Load config ──────────────────────────────────────────────────────────────
CONFIG_PATH = Path(__file__).parent / "config.json"

def load_config():
    if not CONFIG_PATH.exists():
        _fatal("config.json not found. Please run setup.bat first.")
    try:
        with open(CONFIG_PATH) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            _fatal("config.json must be a JSON object, not an array or scalar.")
        return data
    except json.JSONDecodeError as e:
        _fatal(f"config.json is invalid JSON: {e}")

cfg            = load_config()
SAMPLE_RATE    = cfg.get("sample_rate", 16000)
CHANNELS       = cfg.get("channels", 1)
OLLAMA_MODEL    = cfg.get("ollama_model", "llama3.2:3b")
ENGINE          = cfg.get("engine", "moonshine").lower()
WHISPER_MODEL   = cfg.get("whisper_model", "large-v3-turbo")
MOONSHINE_MODEL = cfg.get("moonshine_model", "moonshine/base")
PARAKEET_MODEL  = cfg.get("parakeet_model", "nvidia/parakeet-tdt-0.6b-v2")
LANGUAGE        = cfg.get("language", "en")

# Audio quality guards
MIN_RECORD_SECS   = 0.3    # skip ASR for accidental short presses
MOONSHINE_MAX_SECS = 5.0   # Moonshine context window — clip longer audio
_SILENCE_RMS_THRESHOLD = 0.005   # RMS below this is silence
_SILENCE_WINDOW = 1600           # samples per RMS window (0.1 s at 16 kHz)

# Restore LLM toggle from config so the last-chosen state survives restarts.
# Ollama is ONLY started when the user explicitly clicks "LLM Cleanup: ON" in
# the tray menu (_toggle_llm).  It is never started automatically at launch.
_post_process   = cfg.get("post_process", False)

# Audio cue profile — set in config.json as "audio_cue": "subtle|chime|click|scifi|off"
AUDIO_CUE = cfg.get("audio_cue", "subtle")

# Spoken punctuation — replace words like "period" / "new line" with symbols.
# Toggled via right-click menu or config.json "spoken_punctuation": true/false.
_spoken_punct: bool = cfg.get("spoken_punctuation", True)
_auto_learn_enabled: bool = cfg.get("auto_learn", True)
_command_mode: bool = cfg.get("command_mode", False)  # COMMAND vs PURE mode

# Active engine / model — updated live when the user switches from the menu
_current_engine = ENGINE
_current_model  = (MOONSHINE_MODEL if ENGINE == "moonshine"
                   else PARAKEET_MODEL if ENGINE == "parakeet"
                   else WHISPER_MODEL)

# Available model choices shown in the Switch Model submenu
_MOONSHINE_MODELS  = ["moonshine/tiny", "moonshine/base"]
_WHISPER_MODELS    = [
    "tiny.en",
    "small",
    "medium",
    "distil-small.en",    # distil-whisper small  — 6x faster, ~250 MB
    "distil-medium.en",   # distil-whisper medium — great balance, ~400 MB
    "distil-large-v3",    # distil-whisper large  — near large-v3 accuracy, ~670 MB ★ recommended
    "large-v3-turbo",     # 8x faster than large-v3, ~1.5 GB
    "large-v3",
]
_PARAKEET_MODELS   = [
    "nvidia/parakeet-tdt-0.6b-v2",     # 600 M, English — 30x real-time on CPU, ~1.1 GB
    "nvidia/parakeet-tdt-1.1b",        # 1.1 B, English — highest accuracy, ~2.2 GB
]

# Probe NeMo availability once at startup — used to grey-out Parakeet menu items
try:
    import importlib.util as _ilu
    _nemo_available = _ilu.find_spec("nemo") is not None
except Exception:
    _nemo_available = False

def _save_config_key(key: str, value):
    """Persist a single config value back to config.json."""
    _save_config_keys({key: value})


def _save_config_keys(updates: dict):
    """Persist multiple config values in a single read-write cycle."""
    try:
        with open(CONFIG_PATH) as f:
            data = json.load(f)
        data.update(updates)
        with open(CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=4)
        for k, v in updates.items():
            log.info(f"Config saved: {k} = {v!r}")
    except Exception as e:
        log.error(f"FAILED to save config ({updates!r}): {e}")

# ─── History & Dictionary ─────────────────────────────────────────────────────

_HISTORY_PATH = Path(__file__).parent / "history.json"
_DICT_PATH    = Path(__file__).parent / "dictionary.json"
_MAX_HISTORY  = 50

_history:    list[dict] = []   # [{"text": "...", "ts": "2026-03-24 10:00", "engine": "whisper"}]
_dictionary: dict[str, str] = {}  # {"kate": "CAIT", "llm": "LLM", ...}
_last_transcription: str = ""   # used by Alt+Shift+Z re-paste

# ── Auto-dictionary correction state ─────────────────────────────────────────
_PENDING_PATH = Path(__file__).parent / "pending_corrections.json"
_CONFIDENCE_THRESHOLD = 2   # need N identical corrections before auto-learning
_correction_original: str = ""    # the raw text that was just pasted
_correction_active: bool = False  # True while we're watching for a correction
_correction_watch_cancel_id = None  # after-id for the 30-s auto-cancel timer
_correction_debounce: bool = False  # prevents multiple Enter presses from spawning parallel diffs


def _ui_after(ms, func, *args):
    """Schedule *func* on the Tk main thread.  Safe to call from any thread —
    silently drops the call if the widget or root is already destroyed."""
    try:
        if _widget and _widget.root:
            _widget.root.after(ms, func, *args)
    except Exception:
        pass


def _load_history():
    global _history
    try:
        if _HISTORY_PATH.exists():
            _history = json.loads(_HISTORY_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"Could not load history: {e}")


def _save_history(new_entry: dict | None = None):
    """Save history to disk.  If *new_entry* is given, re-read the file first
    (to pick up deletions from the history window subprocess), append the new
    entry, and write back.  Otherwise just flush the in-memory list."""
    global _history
    try:
        if new_entry is not None:
            # Re-read from disk so subprocess deletions are preserved
            disk = []
            if _HISTORY_PATH.exists():
                disk = json.loads(_HISTORY_PATH.read_text(encoding="utf-8"))
            disk.append(new_entry)
            disk = disk[-_MAX_HISTORY:]
            _history = disk          # keep in-memory list in sync
        _HISTORY_PATH.write_text(
            json.dumps(_history[-_MAX_HISTORY:], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        log.warning(f"Could not save history: {e}")


def _load_dictionary():
    global _dictionary
    try:
        if _DICT_PATH.exists():
            _dictionary = json.loads(_DICT_PATH.read_text(encoding="utf-8"))
            log.info(f"Dictionary loaded: {len(_dictionary)} entries")
    except Exception as e:
        log.warning(f"Could not load dictionary: {e}")


def _atomic_write(path: Path, data):
    """Write JSON atomically via temp-file + rename to avoid half-written reads."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _save_dictionary():
    global _dict_mtime
    try:
        _atomic_write(_DICT_PATH, dict(sorted(_dictionary.items())))
        _dict_mtime = _DICT_PATH.stat().st_mtime
    except Exception as e:
        log.warning(f"Could not save dictionary: {e}")


_dict_mtime: float = 0.0   # tracks dictionary.json mtime to avoid unnecessary re-reads

def _reload_dictionary_if_changed():
    """Re-read dictionary from disk only if the file changed since last check."""
    global _dict_mtime
    try:
        if not _DICT_PATH.exists():
            return
        mt = _DICT_PATH.stat().st_mtime
        if mt != _dict_mtime:
            _dict_mtime = mt
            _load_dictionary()
    except Exception:
        pass


_WORD_RE = re.compile(r"[\w'\u2019-]+")   # compiled once; matches words + apostrophes + hyphens


def _apply_dictionary(text: str) -> str:
    """Replace words in text according to the personal dictionary (case-preserving)."""
    # Re-read from disk only if the file changed (mtime check)
    _reload_dictionary_if_changed()
    if not _dictionary:
        return text

    def _replace(m):
        word = m.group(0)
        key  = re.sub(r"[^\w'-]", "", word).lower()
        repl = _dictionary.get(key)
        if repl is None:
            return word
        # Preserve capitalisation: ALL-CAPS → ALL-CAPS, Title → Title, lower → lower
        if word.isupper():
            return repl.upper()
        if word[0].isupper():
            return repl[0].upper() + repl[1:]
        return repl

    return _WORD_RE.sub(_replace, text)


# ─── Spoken punctuation ───────────────────────────────────────────────────────
# Ordered longest-phrase-first so "exclamation mark" matches before "exclamation".
# Patterns are compiled once at import time.
_PUNCT_REPLACEMENTS = [
    (r"\bexclamation\s+(?:mark|point)\b", "!"),
    (r"\bquestion\s+mark\b",              "?"),
    (r"\bfull\s+stop\b",                  "."),
    (r"\bnew\s+paragraph\b",              "\n\n"),
    (r"\bnew\s+line\b",                   "\n"),
    (r"\bopen\s+(?:bracket|parenthesis|paren)\b", "("),
    (r"\bclose\s+(?:bracket|parenthesis|paren)\b", ")"),
    (r"\bopen\s+quote\b",                 "\u201c"),   # "
    (r"\bclose\s+quote\b",                "\u201d"),   # "
    (r"\bem\s+dash\b",                    "\u2014"),   # —
    (r"\bperiod\b",                       "."),
    (r"\bcomma\b",                        ","),
    (r"\bexclamation\b",                  "!"),
    (r"\bcolon\b",                        ":"),
    (r"\bsemicolon\b",                    ";"),
    (r"\bellipsis\b",                     "..."),
    (r"\bdash\b",                         "-"),
]
_PUNCT_PATTERNS = [(re.compile(p, re.IGNORECASE), r) for p, r in _PUNCT_REPLACEMENTS]


def _apply_spoken_punctuation(text: str) -> str:
    """Replace spoken punctuation words with their symbols.

    Examples (case-insensitive):
      "hello comma how are you period"  →  "hello, how are you."
      "new paragraph dear John"         →  "\\n\\ndear John"
    Skipped entirely when _spoken_punct is False.
    """
    if not _spoken_punct:
        return text
    for pattern, symbol in _PUNCT_PATTERNS:
        text = pattern.sub(symbol, text)
    # Clean up stray spaces that land before punctuation after substitution
    text = re.sub(r" +([.,!?:;])", r"\1", text)
    return text.strip()


def _toggle_spoken_punctuation():
    """Toggle spoken punctuation on/off and persist to config."""
    global _spoken_punct
    _spoken_punct = not _spoken_punct
    _save_config_key("spoken_punctuation", _spoken_punct)
    log.info(f"Spoken punctuation {'enabled' if _spoken_punct else 'disabled'}")
    if _widget:
        _widget.root.after(0, _widget._rebuild_menu)


# Punctuation characters to strip when comparing words for dictionary learning.
# Includes smart quotes and dashes inserted by _apply_spoken_punctuation().
_STRIP_PUNCT = str.maketrans("", "", ".,!?;:\"'\u201c\u201d\u2018\u2019\u2014\u2013\u2026()[]")


def _words_sound_similar(a: str, b: str) -> bool:
    """Return True if two words are similar enough to be a plausible dictation correction.

    Rules (stdlib only):
      • Length difference ≤ 3 characters  (rejects 'cat'→'banana')
      • Character-level similarity ≥ 0.40  (SequenceMatcher ratio)

    The old same-first-letter rule was intentionally removed — it blocked
    legitimate corrections like 'kate'→'cait' (K-sound written two ways).
    The confidence threshold (_CONFIDENCE_THRESHOLD = 2) is the real guard
    against accidental one-off corrections being promoted to the dictionary.
    """
    a, b = a.lower().translate(_STRIP_PUNCT), b.lower().translate(_STRIP_PUNCT)
    if not a or not b or abs(len(a) - len(b)) > 3:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.40


def _load_pending_corrections() -> dict[str, dict]:
    """Load pending correction counts: { "misheard→correct": {"count": N} }"""
    try:
        if _PENDING_PATH.exists():
            return json.loads(_PENDING_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_pending_corrections(pending: dict[str, dict]):
    try:
        _atomic_write(_PENDING_PATH, pending)
    except Exception as e:
        log.warning(f"Could not save pending corrections: {e}")


def _toggle_auto_learn():
    """Toggle auto-learning on/off and persist to config."""
    global _auto_learn_enabled
    _auto_learn_enabled = not _auto_learn_enabled
    _save_config_key("auto_learn", _auto_learn_enabled)
    log.info(f"Auto-learning {'enabled' if _auto_learn_enabled else 'disabled'}")
    if _widget:
        _widget.root.after(0, _widget._rebuild_menu)


def _toggle_command_mode():
    """Toggle between PURE dictation and COMMAND mode.
    PURE (default): every utterance is dictated verbatim (v1.x behaviour).
    COMMAND: utterances are classified, commands are executed, text still
    gets dictated when the classifier says it is not a command.
    """
    global _command_mode
    _command_mode = not _command_mode
    _save_config_key("command_mode", _command_mode)
    log.info(f"Mode switched to {'COMMAND' if _command_mode else 'PURE'}")
    if _widget:
        _widget.root.after(0, _widget._rebuild_menu)
        _widget.root.after(0, _widget._refresh_idle_color)


def _toggle_two_pass():
    """Toggle two-pass transcription on/off and persist to config.
    When turning ON, loads the background engine lazily if not already loaded.
    When turning OFF, the reference is dropped so GC can reclaim the memory."""
    global _two_pass_enabled, _bg_asr_model
    _two_pass_enabled = not _two_pass_enabled
    _save_config_key("two_pass", _two_pass_enabled)
    log.info(f"Two-pass {'enabled' if _two_pass_enabled else 'disabled'}")
    if _two_pass_enabled and _bg_asr_model is None:
        # Load lazily in background
        threading.Thread(target=_load_bg_asr, daemon=True, name="bg-model-load").start()
    elif not _two_pass_enabled:
        with _bg_asr_lock:
            _bg_asr_model = None
        log.info("[TwoPass] background engine reference released")
    if _widget:
        _widget.root.after(0, _widget._rebuild_menu)


def _start_correction_watch(original_text: str):
    """Arm the correction watcher.  After paste, we remember the original
    transcription and wait for the user to press Enter, which signals
    they've finished editing.  The Enter handler then diffs and learns.

    While armed the idle dot turns amber so the user can see the app is
    ready to learn.  The watch auto-cancels after 30 s if Enter is never pressed."""
    global _correction_original, _correction_active, _correction_watch_cancel_id
    if not _auto_learn_enabled:
        return
    _correction_original = original_text
    _correction_active = True
    log.info("[AutoDict] watching for corrections (press Enter to commit)")

    if _widget:
        # Amber dot — show the watch is armed
        _ui_after(0, _widget._refresh_idle_color)
        # Auto-cancel after 30 s so the amber dot doesn't stay forever
        if _correction_watch_cancel_id is not None:
            try:
                _widget.root.after_cancel(_correction_watch_cancel_id)
            except Exception:
                pass
        _correction_watch_cancel_id = _widget.root.after(30_000, _cancel_correction_watch_timeout)


def _cancel_correction_watch_timeout():
    """Auto-cancel the correction watch after 30 s of inactivity."""
    global _correction_active, _correction_watch_cancel_id
    _correction_active = False
    _correction_watch_cancel_id = None
    log.info("[AutoDict] correction watch timed out")
    _ui_after(0, _widget._refresh_idle_color) if _widget else None


def _on_enter_correction():
    """Called when Enter is pressed while correction watch is active.

    Strategy:
    1. Check whether the clipboard changed since we pasted (user manually
       copied their corrected text — simplest case).
    2. If the clipboard is unchanged, try Ctrl+A → Ctrl+C to grab whatever
       is currently in the focused field (works in most text inputs).
    3. Restore the clipboard so we don't clobber the user's data.
    4. Diff the corrected text against what we originally pasted and learn
       any word-level changes.
    """
    global _correction_active, _correction_watch_cancel_id, _correction_debounce
    if not _correction_active or _correction_debounce:
        return
    _correction_debounce = True
    _correction_active = False
    # Cancel the auto-timeout job now that Enter was pressed
    if _correction_watch_cancel_id is not None and _widget:
        try:
            _widget.root.after_cancel(_correction_watch_cancel_id)
        except Exception:
            pass
        _correction_watch_cancel_id = None
    # Revert amber dot immediately
    if _widget:
        _ui_after(0, _widget._refresh_idle_color)

    original = _correction_original   # = final_text (what was actually pasted)
    if not original:
        return

    # Give the Enter keypress a moment to land before reading the clipboard
    time.sleep(0.15)

    try:
        clipboard_now = pyperclip.paste().strip()
    except Exception:
        return

    corrected = None

    if clipboard_now and clipboard_now != original:
        # User explicitly copied their corrected text — use it directly
        corrected = clipboard_now
        log.info("[AutoDict] correction found in clipboard")
    else:
        # Clipboard unchanged — user edited in-place without copying.
        # Send Ctrl+A then Ctrl+C to grab the full current field content,
        # then restore the clipboard so we don't clobber anything.
        try:
            keyboard.send("ctrl+a")
            time.sleep(0.08)
            keyboard.send("ctrl+c")
            time.sleep(0.12)
            corrected = pyperclip.paste().strip()
            # Restore clipboard to what we originally pasted
            pyperclip.copy(original)
            log.info("[AutoDict] grabbed field content via Ctrl+A/Ctrl+C")
            # Guard: if the grabbed text is > 3× longer than the original,
            # Ctrl+A selected the whole document (email body, long note, etc.)
            # rather than just the pasted sentence — discard and bail out.
            if corrected and len(corrected.split()) > len(original.split()) * 3:
                log.warning("[AutoDict] Ctrl+A grabbed too much context — skipping")
                return
        except Exception as e:
            log.warning(f"[AutoDict] could not grab field content: {e}")
            return

    if not corrected or corrected == original:
        log.info("[AutoDict] no correction detected")
        _correction_debounce = False
        return

    _diff_and_learn(original, corrected)
    _correction_debounce = False


def _diff_and_learn(original: str, corrected: str):
    """Fuzzy word-level diff between original transcription and corrected text.
    Words that differ and sound similar are candidates for dictionary learning.
    Each candidate must be seen _CONFIDENCE_THRESHOLD times before promotion."""
    orig_words = original.split()
    corr_words = corrected.split()

    # Use SequenceMatcher for word-level alignment (handles insertions/deletions)
    sm = difflib.SequenceMatcher(None, orig_words, corr_words)
    candidates: list[tuple[str, str]] = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            # Pair up replaced words 1:1
            for ow, cw in zip(orig_words[i1:i2], corr_words[j1:j2]):
                ok = ow.lower().translate(_STRIP_PUNCT)
                ck = cw.lower().translate(_STRIP_PUNCT)
                if ok and ck and ok != ck:
                    candidates.append((ok, ck))
        # insert / delete — not a correction, skip

    if not candidates:
        log.info("[AutoDict] diff found no word-level corrections")
        return

    pending = _load_pending_corrections()
    promoted = []

    for orig_w, corr_w in candidates:
        # Phonetic similarity gate — skip obviously unrelated words
        if not _words_sound_similar(orig_w, corr_w):
            log.info(f"[AutoDict] skipping '{orig_w}' → '{corr_w}' (not similar)")
            continue

        key = f"{orig_w}→{corr_w}"
        entry = pending.get(key, {"count": 0})
        entry["count"] += 1
        pending[key] = entry

        if entry["count"] >= _CONFIDENCE_THRESHOLD:
            # Promote to dictionary
            _dictionary[orig_w] = corr_w
            _save_dictionary()
            pending.pop(key, None)
            promoted.append((orig_w, corr_w))
            log.info(f"[AutoDict] PROMOTED to dictionary: '{orig_w}' → '{corr_w}'")
        else:
            remaining = _CONFIDENCE_THRESHOLD - entry["count"]
            log.info(f"[AutoDict] pending: '{orig_w}' → '{corr_w}' "
                     f"(count={entry['count']}, need {remaining} more)")

    _save_pending_corrections(pending)

    # Show toast for promoted entries
    if promoted and _widget:
        for orig_w, corr_w in promoted:
            _ui_after(0, _widget._notify_dict_learned, orig_w, corr_w)


CLEANUP_PROMPT = """You are a dictation post-processor. Clean up the following raw speech transcript:
- Remove filler words (um, uh, like, you know, basically, so)
- Fix grammar and sentence structure naturally
- Add proper punctuation
- Preserve the speaker's meaning and tone exactly
- Output ONLY the cleaned text, nothing else

Raw transcript:
{transcript}"""

def _trim_silence(audio: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Trim leading and trailing silence from audio using a rolling RMS window.
    Returns the trimmed array (at least MIN_RECORD_SECS long)."""
    win = _SILENCE_WINDOW
    n   = len(audio)
    if n < win:
        return audio
    # Find first window above threshold (start of speech)
    start = 0
    for i in range(0, n - win, win):
        rms = float(np.sqrt(np.mean(audio[i:i + win] ** 2)))
        if rms >= _SILENCE_RMS_THRESHOLD:
            start = max(0, i - win)   # keep one window of lead-in
            break
    # Find last window above threshold (end of speech)
    end = n
    for i in range(n - win, start, -win):
        rms = float(np.sqrt(np.mean(audio[i:i + win] ** 2)))
        if rms >= _SILENCE_RMS_THRESHOLD:
            end = min(n, i + 2 * win)   # keep one window of trail
            break
    min_samples = int(MIN_RECORD_SECS * sr)
    if end - start < min_samples:
        return audio   # don't trim to nothing
    return audio[start:end]


# ─── Load ASR model ───────────────────────────────────────────────────────────
#
# Each engine is wrapped in a thin class that exposes a single method:
#   .transcribe(audio_1d: np.ndarray) -> str
# This keeps the engine-switching logic entirely inside the wrappers.

class _MoonshineEngine:
    def __init__(self, model_name: str):
        from moonshine_onnx import MoonshineOnnxModel
        from moonshine_onnx.transcribe import load_tokenizer
        self._model = MoonshineOnnxModel(model_name=model_name)
        self._tokenizer = load_tokenizer()

    # ── Custom generate that fixes the encoder_attention_mask shape bug ────────
    # The library's generate() uses np.ones_like(audio) for the mask, giving
    # shape (1, num_audio_samples).  But the decoder's cross-attention expects
    # the mask to match the *encoder output* sequence length (after downsampling),
    # not the raw audio length.  Passing the wrong shape causes the first decoder
    # step to produce near-uniform logits where EOS wins, returning [BOS, EOS].
    def _generate(self, audio_batch: np.ndarray, max_len: int = 192):
        m = self._model

        # ── Encoder ───────────────────────────────────────────────────────────
        enc_in = {"input_values": audio_batch}
        if "attention_mask" in m.encoder_input_names:
            enc_in["attention_mask"] = np.ones_like(audio_batch, dtype=np.int64)
        last_hidden_state = m.encoder.run(None, enc_in)[0]   # (1, T_enc, D)

        # Attention mask sized to the *encoder output* sequence length
        enc_seq_len = last_hidden_state.shape[1]
        enc_attn_mask = np.ones((audio_batch.shape[0], enc_seq_len), dtype=np.int64)

        # ── Initial KV cache ──────────────────────────────────────────────────
        past_kv = {
            f"past_key_values.{i}.{a}.{b}": np.zeros(
                (0, m.num_key_value_heads, 1, m.head_dim), dtype=np.float32
            )
            for i in range(m.num_layers)
            for a in ("decoder", "encoder")
            for b in ("key", "value")
        }

        tokens = [m.decoder_start_token_id]
        input_ids = [[m.decoder_start_token_id]]

        for step in range(max_len):
            use_cache = step > 0
            dec_in = dict(
                input_ids=input_ids,
                encoder_hidden_states=last_hidden_state,
                use_cache_branch=[use_cache],
                **past_kv,
            )
            if "encoder_attention_mask" in m.decoder_input_names:
                dec_in["encoder_attention_mask"] = enc_attn_mask

            logits, *present_kv = m.decoder.run(None, dec_in)
            next_token = int(logits[0, -1].argmax())
            tokens.append(next_token)
            if next_token == m.eos_token_id:
                break

            # ── Repetition-loop guard ─────────────────────────────────────────
            # Greedy decoding can enter a cycle where the same N-token sequence
            # repeats forever (e.g. "CaitOS Qwen Stellantis Fenekie CaitOS …").
            # Check whether the last window of tokens is an exact repeat of the
            # window immediately before it; if so, we're in a loop — stop early.
            if len(tokens) >= 16:
                for cycle in range(2, 9):          # test cycle lengths 2–8 tokens
                    tail = tokens[-cycle:]
                    prev = tokens[-(cycle * 2):-cycle]
                    if tail == prev:
                        log.warning(
                            f"Moonshine repetition loop detected "
                            f"(cycle={cycle} tokens) — stopping generation early"
                        )
                        return [tokens[:-cycle]]   # strip the repeated tail

            input_ids = [[next_token]]
            for k, v in zip(past_kv.keys(), present_kv):
                if not use_cache or "decoder" in k:
                    past_kv[k] = v

        return [tokens]

    def _transcribe_chunk(self, chunk: np.ndarray) -> str:
        """Transcribe one chunk that fits within Moonshine's 5-second window."""
        audio = np.ascontiguousarray(chunk, dtype=np.float32)
        peak  = float(np.max(np.abs(audio)))
        if peak > 0.001:
            audio = audio * (0.5 / peak)

        tokens = self._generate(audio[np.newaxis, :])

        if hasattr(tokens, "tolist"):
            tokens = tokens.tolist()
        if tokens and not isinstance(tokens[0], (list, tuple)):
            tokens = [tokens]
        tokens = [[int(t) for t in seq] for seq in tokens]

        texts = self._tokenizer.decode_batch(tokens)
        return " ".join(t.strip() for t in texts).strip()

    def transcribe(self, audio_1d: np.ndarray) -> str:
        # Trim leading/trailing silence before feeding Moonshine's short context window
        audio_in    = _trim_silence(np.ascontiguousarray(audio_1d, dtype=np.float32))
        max_samples = int(MOONSHINE_MAX_SECS * SAMPLE_RATE)
        min_samples = int(MIN_RECORD_SECS   * SAMPLE_RATE)

        if len(audio_in) <= max_samples:
            # Short enough to process in one shot
            return self._transcribe_chunk(audio_in)

        # Long recording: split into overlapping chunks, transcribe each, join.
        # Overlap prevents splitting words at chunk boundaries.
        overlap  = int(0.5 * SAMPLE_RATE)   # 0.5 s overlap
        step     = max_samples - overlap
        n_chunks = math.ceil(max(1, len(audio_in) - overlap) / step)
        log.info(f"Long audio {len(audio_in)/SAMPLE_RATE:.1f}s → {n_chunks} chunks of ≤{MOONSHINE_MAX_SECS:.0f}s (overlap {overlap/SAMPLE_RATE:.1f}s)")
        parts: list[str] = []
        for start in range(0, len(audio_in), step):
            chunk = audio_in[start : start + max_samples]
            if len(chunk) < min_samples:
                break                       # skip tiny tail (< 0.3 s)
            text = self._transcribe_chunk(chunk)
            if text:
                # Deduplicate overlapping words at join points
                if parts:
                    prev_words = parts[-1].split()
                    curr_words = text.split()
                    # Check if the last N words of previous chunk match
                    # the first N words of current chunk (overlap artefact)
                    best = 0
                    for n in range(1, min(6, len(prev_words), len(curr_words)) + 1):
                        if prev_words[-n:] == curr_words[:n]:
                            best = n
                    if best > 0:
                        text = " ".join(curr_words[best:])
                if text:
                    parts.append(text)
        return " ".join(parts)


class _WhisperEngine:
    def __init__(self, model_name: str):
        from faster_whisper import WhisperModel
        self._model = WhisperModel(model_name, device="cpu", compute_type="int8")

    def transcribe(self, audio_1d: np.ndarray) -> str:
        audio = audio_1d.astype(np.float32)
        # Build initial_prompt from dictionary entries to bias recognition
        hint = " ".join(_dictionary.values()) if _dictionary else None
        segments, _ = self._model.transcribe(
            audio,
            language=LANGUAGE,
            vad_filter=True,
            beam_size=1,
            temperature=0,
            condition_on_previous_text=False,
            initial_prompt=hint,
        )
        return " ".join(seg.text for seg in segments).strip()


class _ParakeetEngine:
    """NVIDIA Parakeet TDT — 30× faster than real-time on CPU, English.

    Requires:  pip install nemo_toolkit[asr]
    First run downloads the model weights from HuggingFace (~1.1 GB or ~2.2 GB).
    """

    def __init__(self, model_name: str):
        try:
            import nemo.collections.asr as nemo_asr
        except ImportError:
            raise ImportError(
                "NeMo is not installed. Run:\n"
                "  pip install nemo_toolkit[asr]\n"
                "and restart cait-whisper."
            )
        log.info(f"Parakeet: loading {model_name} (first run downloads weights)…")
        self._model = nemo_asr.models.ASRModel.from_pretrained(model_name)
        self._model.eval()

    def transcribe(self, audio_1d: np.ndarray) -> str:
        # Try direct numpy array transcription first; fall back to temp file
        # if the NeMo version doesn't support it.
        audio = audio_1d.astype(np.float32)
        try:
            results = self._model.transcribe(audio=[audio])
        except TypeError:
            # Older NeMo — fall back to temp WAV file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                sf.write(tmp_path, audio, SAMPLE_RATE)
                results = self._model.transcribe([tmp_path])
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
        # NeMo returns a list; each element may be a str or a Hypothesis object
        if results:
            r = results[0]
            return (r.text if hasattr(r, "text") else str(r)).strip()
        return ""


def _load_asr():
    model_name = MOONSHINE_MODEL if ENGINE == "moonshine" else WHISPER_MODEL
    if ENGINE == "moonshine":
        log.info(f"Loading Moonshine ({model_name})...")
        try:
            engine = _MoonshineEngine(model_name)
            log.info(f"✓ Moonshine ({model_name}) ready")
            return engine
        except ImportError as e:
            _fatal(f"Missing package for Moonshine: {e}\n\nRun setup.bat to install dependencies.", e)
        except Exception as e:
            _fatal(f"Moonshine failed to load: {e}", e)
    elif ENGINE == "parakeet":
        pk_model = cfg.get("parakeet_model", _PARAKEET_MODELS[0])
        log.info(f"Loading Parakeet ({pk_model})...")
        try:
            engine = _ParakeetEngine(pk_model)
            log.info(f"✓ Parakeet ({pk_model}) ready")
            return engine
        except ImportError as e:
            _fatal(f"Missing package for Parakeet: {e}", e)
        except Exception as e:
            _fatal(f"Parakeet failed to load: {e}", e)
    else:
        log.info(f"Loading Whisper ({model_name})...")
        try:
            engine = _WhisperEngine(model_name)
            log.info(f"✓ Whisper ({model_name}) ready")
            return engine
        except ImportError as e:
            _fatal(f"Missing package for Whisper: {e}\n\nRun setup.bat to install dependencies.", e)
        except Exception as e:
            _fatal(f"Whisper failed to load: {e}", e)

# _asr_model is set inside main() — do NOT load at module level under pythonw
_asr_model = None
# Lock guards all reads/writes to _asr_model across the model-load, model-switch,
# and transcription threads so we never call .transcribe() on a half-swapped object.
_asr_lock  = threading.Lock()

# ─── Two-pass transcription (v2.1) ────────────────────────────────────────────
# When _two_pass_enabled and the primary engine is Moonshine, we also load a
# second (more accurate) Whisper engine. After each paste, the background engine
# re-transcribes the same audio. If the result differs meaningfully, the user
# gets a toast and Alt+Shift+Z re-pastes the improved version.
#
# Using a SEPARATE engine instance with its own lock is deliberate: it means the
# next recording is never blocked waiting on a background Whisper call, which is
# the whole point of fast+slow two-pass.
_bg_asr_model = None
_bg_asr_lock  = threading.Lock()
_two_pass_enabled: bool = cfg.get("two_pass", True)

# ─── Transcription helper ─────────────────────────────────────────────────────

def _run_asr(audio: np.ndarray) -> str:
    """Flatten audio to 1-D float32 and dispatch to the active engine."""
    with _asr_lock:
        if _asr_model is None:
            return ""
        return _asr_model.transcribe(audio.flatten().astype(np.float32))


# ─── Two-pass: background loader / runner / callback ──────────────────────

def _load_bg_asr():
    """Load the background Whisper engine for two-pass transcription.
    Runs in its own daemon thread; never blocks startup. Skips silently if
    two-pass is disabled or the primary engine is already Whisper / Parakeet
    (in which case a second pass adds no value)."""
    global _bg_asr_model
    if not _two_pass_enabled:
        log.info("[TwoPass] disabled in config; skipping background load")
        return
    if _current_engine != "moonshine":
        log.info(f"[TwoPass] primary engine is {_current_engine}; no background pass needed")
        return
    try:
        t0 = time.perf_counter()
        log.info(f"[TwoPass] loading background Whisper ({WHISPER_MODEL})...")
        engine = _WhisperEngine(WHISPER_MODEL)
        with _bg_asr_lock:
            _bg_asr_model = engine
        log.info(f"[TwoPass] background Whisper ready in {time.perf_counter() - t0:.1f}s")
    except Exception as e:
        log.warning(f"[TwoPass] failed to load background engine: {e}")


def _run_bg_asr(audio_flat: np.ndarray, original_text: str):
    """Re-transcribe audio on the background engine. Called from a daemon thread
    after the main paste has already happened, so we are never on the hot path."""
    if _bg_asr_model is None or not _two_pass_enabled:
        return
    try:
        with _bg_asr_lock:
            if _bg_asr_model is None:
                return
            t0 = time.perf_counter()
            bg_text = _bg_asr_model.transcribe(audio_flat).strip()
            log.info(f"[TwoPass] bg ASR in {time.perf_counter() - t0:.2f}s: {bg_text!r}")
        _on_better_transcription(bg_text, original_text)
    except Exception as e:
        log.warning(f"[TwoPass] background ASR failed: {e}")


def _on_better_transcription(bg_text: str, original_text: str):
    """Compare the background result with the fast-pasted original. If the
    background version is meaningfully better, update _last_transcription and
    show a toast so the user can re-paste via Alt+Shift+Z."""
    if not bg_text:
        return
    if bg_text == original_text:
        return
    # Normalize for comparison: lowercase + strip punctuation
    norm_bg   = re.sub(r"[^\w\s]", "", bg_text).lower().strip()
    norm_orig = re.sub(r"[^\w\s]", "", original_text).lower().strip()
    if norm_bg == norm_orig:
        log.info("[TwoPass] bg text identical after normalization; no update")
        return
    ratio = difflib.SequenceMatcher(None, bg_text, original_text).ratio()
    if ratio >= 0.90:
        log.info(f"[TwoPass] bg similar (ratio={ratio:.2f}); skipping toast")
        return
    log.info(f"[TwoPass] better transcription available (ratio={ratio:.2f})")
    # Update _last_transcription so Alt+Shift+Z pastes the improved version
    global _last_transcription
    _last_transcription = bg_text
    if _widget:
        _ui_after(0, _widget._notify_bg_transcription, bg_text)


# ─── Audio cues ───────────────────────────────────────────────────────────────
#
# Four profiles — pick in config.json: "audio_cue": "subtle|chime|click|scifi|off"
# Each profile defines a "start" (recording begins) and "done" (text pasted) tone.
# Tones are generated on-the-fly with numpy; no extra audio files needed.

_CUE_PROFILES: dict = {
    # Gentle frequency-sweep tones — unobtrusive in an office
    "subtle": {
        "start": dict(f0=600,  f1=820,  dur=0.09, amp=0.22),
        "done":  dict(f0=820,  f1=580,  dur=0.11, amp=0.22),
    },
    # Softer bell-like pitches inspired by notification sounds
    "chime": {
        "start": dict(f0=1047, f1=1319, dur=0.16, amp=0.26),   # C6 → E6
        "done":  dict(f0=1319, f1=1047, dur=0.18, amp=0.26),   # E6 → C6
    },
    # Very brief transients — almost subliminal
    "click": {
        "start": dict(f0=1400, f1=1400, dur=0.028, amp=0.38),
        "done":  dict(f0=900,  f1=900,  dur=0.028, amp=0.38),
    },
    # Wide sweep — matches the futuristic waveform aesthetic
    "scifi": {
        "start": dict(f0=380,  f1=1100, dur=0.13, amp=0.24),
        "done":  dict(f0=1100, f1=280,  dur=0.16, amp=0.24),
    },
}


def _play_cue(event: str, profile: str | None = None):
    """Play a short non-blocking audio cue.  event = 'start' or 'done'."""
    p_name = profile or AUDIO_CUE
    if p_name == "off":
        return
    cue = _CUE_PROFILES.get(p_name, _CUE_PROFILES["subtle"]).get(event)
    if not cue:
        return
    try:
        sr  = 44100
        dur = cue["dur"]
        t   = np.linspace(0, dur, int(sr * dur), endpoint=False)
        # Frequency sweep via cumulative-phase integration
        freq  = np.linspace(cue["f0"], cue["f1"], len(t))
        phase = np.cumsum(2 * np.pi * freq / sr)
        wave  = np.sin(phase)
        # Short attack + exponential decay envelope
        attack = int(sr * 0.006)
        env = np.exp(-t * (5.5 / dur))
        env[:attack] *= np.linspace(0, 1, attack)
        audio = (wave * env * cue["amp"]).astype(np.float32)
        sd.play(audio, sr, blocking=False)
    except Exception as e:
        log.warning(f"Audio cue '{event}' failed: {e}")


def _set_audio_cue(profile: str):
    """Switch the active audio-cue profile and persist to config."""
    global AUDIO_CUE
    AUDIO_CUE = profile
    _save_config_key("audio_cue", profile)
    log.info(f"Audio cue set to: {profile}")
    if _widget:
        _widget.root.after(0, _widget._rebuild_menu)


# ─── Live model switching ─────────────────────────────────────────────────────

def _switch_model(engine: str, model: str):
    """Switch ASR engine/model at runtime (non-blocking — loads in background)."""
    global _asr_model, _current_engine, _current_model

    log.info(f"_switch_model called: engine={engine!r} model={model!r} "
             f"(current: {_current_engine!r}/{_current_model!r})")

    if engine == _current_engine and model == _current_model:
        log.info("Already on requested model — no-op")
        return  # already active — nothing to do

    if _recording or _processing:
        log.warning(f"Blocked: cannot switch model while recording={_recording} processing={_processing}")
        return

    log.info(f"Switching model: {engine} ({model})…")
    if _widget:
        _widget.set_state("processing")

    def _load():
        global _asr_model, _current_engine, _current_model
        try:
            if engine == "moonshine":
                new_engine = _MoonshineEngine(model)
            elif engine == "parakeet":
                new_engine = _ParakeetEngine(model)
            else:
                new_engine = _WhisperEngine(model)
            with _asr_lock:
                _asr_model    = new_engine
                _current_engine = engine
                _current_model  = model
            model_key = {"moonshine": "moonshine_model",
                         "parakeet": "parakeet_model"}.get(engine, "whisper_model")
            _save_config_keys({"engine": engine, model_key: model})
            log.info(f"✓ Model switched to {engine} ({model})")
        except Exception as exc:
            err = str(exc)
            # Detect incomplete HuggingFace download (model.bin missing after interrupted fetch)
            if "Unable to open file" in err and "model.bin" in err:
                # Error format: "Unable to open file 'model.bin' in model 'PATH'"
                # Extract the snapshot folder (the second quoted string)
                m = re.search(r"in model '([^']+)'", err)
                snap_folder = m.group(1) if m else "<path not found — check log above>"
                log.error(
                    f"Incomplete model download for '{model}'.\n"
                    f"  Delete the broken cache folder and switch again to re-download:\n"
                    f"  rd /s /q \"{snap_folder}\""
                )
            else:
                log.error(f"Model switch failed: {exc}")
        finally:
            if _widget:
                # Refresh menus to show updated checkmark, then return to idle
                _ui_after(0, _widget._rebuild_menu)
                _widget.set_state("idle")

    threading.Thread(target=_load, daemon=True, name="model-switch").start()


# ─── Ollama process management ────────────────────────────────────────────────
# Ollama is started on-demand when LLM cleanup is enabled and stopped when it
# is disabled.  We only kill the process if WE started it; a pre-existing
# Ollama instance (e.g. from autostart) is left untouched when we exit.

_ollama_proc = None   # subprocess.Popen handle, set only if we launched it


def _start_ollama_service():
    """Ensure the Ollama service is running. No-op if already responsive."""
    global _ollama_proc
    import subprocess
    try:
        import ollama as _ol
        _ol.list()          # cheap ping — succeeds if service is already up
        log.info("Ollama already running")
        return
    except Exception:
        pass
    try:
        log.info("Starting Ollama service...")
        _ollama_proc = subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(2)       # give it a moment to bind the port
        log.info("Ollama service started")
    except FileNotFoundError:
        log.warning("ollama executable not found — LLM cleanup will fail. Run setup.bat.")
    except Exception as exc:
        log.error(f"Could not start Ollama: {exc}")


def _stop_ollama_service():
    """Stop Ollama if we launched it this session."""
    global _ollama_proc
    if _ollama_proc is None:
        log.info("Ollama was not started by cait-whisper — leaving it running")
        return
    try:
        _ollama_proc.terminate()
        log.info("Ollama service stopped")
    except Exception as exc:
        log.error(f"Could not stop Ollama: {exc}")
    finally:
        _ollama_proc = None


# ─── Mouse cursor → monitor work-area helper ─────────────────────────────────

class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize",    ctypes.c_uint),
        ("rcMonitor", ctypes.c_long * 4),
        ("rcWork",    ctypes.c_long * 4),
        ("dwFlags",   ctypes.c_uint),
    ]

def _get_cursor_monitor_workarea():
    """Return the work-area (x, y, w, h) of the monitor that currently
    contains the mouse cursor.  Falls back to the primary monitor if the
    Win32 call fails.  The work-area excludes the taskbar.
    """
    try:
        pt = _POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        hmon = ctypes.windll.user32.MonitorFromPoint(
            pt, 2  # MONITOR_DEFAULTTONEAREST
        )
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            left, top, right, bottom = mi.rcWork
            return left, top, right - left, bottom - top
    except Exception:
        pass
    return None


# ─── Tray icon helpers ────────────────────────────────────────────────────────

_tray_icon_cache: dict[str, Image.Image] = {}

def _make_tray_image(color: str) -> Image.Image:
    """Generate a simple filled circle for the tray icon (cached per color)."""
    cached = _tray_icon_cache.get(color)
    if cached is not None:
        return cached
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=color)
    _tray_icon_cache[color] = img
    return img

_TRAY_COLORS = {
    "idle":       "#2A1A0E",
    "loading":    "#1A1A3E",
    "recording":  "#7A3018",
    "processing": "#6A4A18",
    "done":       "#1A5A38",
    "no_speech":  "#1E1610",
}

# Per-state waveform colours: (wave_color, glow_color, border_color)
# Inspired by Anthropic's warm coral/terracotta brand palette.
_STATE_WAVE = {
    "loading":    ("#6070D0", "#0A0A2E", "#282868"),   # cool indigo pulse — "waking up"
    "recording":  ("#E07040", "#3C1A08", "#6A2E14"),   # warm coral-orange
    "processing": ("#D4A060", "#2E1E06", "#5C3A10"),   # warm amber (thinking)
    "done":       ("#60D890", "#0C2E1A", "#206830"),   # soft mint (complete)
    "no_speech":  ("#2E2218", None,      "#1E160E"),   # barely visible warm gray
    "busy":       ("#D4A060", "#2E1E06", "#5C3A10"),   # amber flash: "not ready yet"
}

# ─── Floating status widget ───────────────────────────────────────────────────
#
# Idle   → tiny 24×24 dot, very transparent — barely there
# Active → compact 130×26 dark strip with animated waveform bars (no text)
#
# Bar animation:
#   recording  → bars driven by live mic RMS, gaussian-enveloped, smoothed
#   processing → slow travelling sine wave
#   done       → all bars high for ~900 ms, then auto-return to idle
#   no_speech  → flat near-zero bars, auto-return after 1.5 s

_W_WAVE,    _H_WAVE = 140, 36   # hold-to-talk: waveform only
_W_WAVE_HF, _H_WAVE = 196, 36   # hands-free:  ✕ + waveform + ● pill
_N_BARS  = 13
_BAR_W   = 4
_BAR_GAP = 2

# ── Appearance — driven by config.json "appearance" section ───────────────────
_ap = cfg.get("appearance", {})

_BG_ACTIVE    = _ap.get("active_bg",           "#1C1612")   # warm near-black
_BORDER_COLOR = _ap.get("active_border_color", "#6A2E14")   # fallback; overridden per-state
_BORDER_PX    = int(_ap.get("active_border_px",  5))
_ACTIVE_ALPHA = float(_ap.get("active_alpha",    0.82))

_IDLE_COLOR   = _ap.get("idle_color", "#3A1E0C")   # dim warm ember — barely there
_IDLE_ALPHA   = float(_ap.get("idle_alpha", 0.45))
_W_DOT = _H_DOT = int(_ap.get("idle_size", 24))


class StatusWidget:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self._anchor_x = sw - 24
        self._anchor_y = sh - 60

        # Idle dot (hidden when active)
        self._dot = tk.Label(self.root, text="◉", font=("Segoe UI", 13, "bold"),
                             padx=0, pady=0)

        # Inner frame — sits 1 px inside the root window so the root bg
        # shows through as a thin border in active states
        self._inner = tk.Frame(self.root, bg=_BG_ACTIVE)

        # Waveform canvas (lives inside _inner; packed dynamically per state)
        self._canvas = tk.Canvas(self._inner, width=_W_WAVE - 2 * _BORDER_PX,
                                 height=_H_WAVE, bg=_BG_ACTIVE, highlightthickness=0)

        # ── Hands-free side buttons — only packed when _hands_free is True ──
        # Left: cancel (discard recording, return to idle)
        self._btn_cancel = tk.Label(
            self._inner, text="✕", font=("Segoe UI", 10, "bold"),
            padx=8, pady=0, cursor="hand2",
            bg=_BG_ACTIVE, fg="#4A2E1A",
        )
        self._btn_cancel.bind("<ButtonRelease-1>", lambda e: _cancel_recording())
        self._btn_cancel.bind("<Enter>", lambda e: self._btn_cancel.config(fg="#E07040"))
        self._btn_cancel.bind("<Leave>", lambda e: self._btn_cancel.config(fg="#4A2E1A"))

        # Right: stop + send (same as releasing Ctrl+Win in hold mode)
        self._btn_stop = tk.Label(
            self._inner, text="⏺", font=("Segoe UI Symbol", 13),
            padx=6, pady=0, cursor="hand2",
            bg=_BG_ACTIVE, fg="#CC3A1A",
        )
        self._btn_stop.bind("<ButtonRelease-1>", lambda e: _stop_and_send())
        self._btn_stop.bind("<Enter>", lambda e: self._btn_stop.config(fg="#FF5533"))
        self._btn_stop.bind("<Leave>", lambda e: self._btn_stop.config(fg="#CC3A1A"))

        # Right-click context menu — built (and rebuilt after model switches) by _rebuild_menu()
        self._menu = tk.Menu(self.root, tearoff=0)
        self._rebuild_menu()

        for w in (self.root, self._dot, self._inner, self._canvas,
                  self._btn_cancel, self._btn_stop):
            w.bind("<ButtonPress-3>", self._show_menu)
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>",     self._drag_move)

        self._anim_job   = None
        self._bar_h        = [0.08] * _N_BARS   # smoothed bar heights 0..1
        self._anim_phase   = 0.0
        self._state        = "idle"

        self.root.protocol("WM_DELETE_WINDOW", _quit)
        self._apply_state("idle")

        # Apply Windows 11 DWM rounded corners (silent no-op on Windows 10)
        self.root.update()
        self._apply_dwm_round_corners()

        # ── Permanent topmost heartbeat ──────────────────────────────────────
        # Re-assert HWND_TOPMOST every 500 ms so the widget ALWAYS stays
        # above every other window, regardless of what else happens on screen.
        self._start_topmost_heartbeat()

    # ── Public ────────────────────────────────────────────────────────────────

    def set_state(self, state: str):
        # Capture _hands_free NOW (in the calling thread) so _apply_state sees
        # the value that was true at the moment of the call, not a later mutation.
        hf = _hands_free
        self.root.after(0, lambda s=state, h=hf: self._apply_state(s, h))

    # ── Private ───────────────────────────────────────────────────────────────

    def _apply_dwm_round_corners(self):
        """Request Windows 11 DWM rounded corners. Silent no-op on Windows 10."""
        try:
            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            DWMWCP_ROUND = 2   # fully rounded — was DWMWCP_ROUNDSMALL=3 (small rounding)
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if not hwnd:
                hwnd = self.root.winfo_id()
            value = ctypes.c_int(DWMWCP_ROUND)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(value), ctypes.sizeof(value),
            )
        except Exception:
            pass  # Windows 10 / unsupported — no-op

    # ── Monitor-aware corner anchoring ──────────────────────────────────────

    _MARGIN_X = 24   # px from the right edge of the work-area
    _MARGIN_Y = 60   # px from the bottom edge

    def _anchor_to_monitor(self):
        """Position the widget at the bottom-right of whichever monitor
        the mouse cursor is on.  Called every 500 ms by the heartbeat."""
        area = _get_cursor_monitor_workarea()
        if area is None:
            return  # keep current position
        mx, my, mw, mh = area
        new_ax = mx + mw - self._MARGIN_X
        new_ay = my + mh - self._MARGIN_Y
        # Only reposition if the anchor actually changed (avoids flicker)
        if new_ax != self._anchor_x or new_ay != self._anchor_y:
            self._anchor_x = new_ax
            self._anchor_y = new_ay
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            self.root.geometry(f"{w}x{h}+{new_ax - w}+{new_ay - h}")

    def _is_offscreen(self) -> bool:
        """Return True if the widget is positioned outside all visible monitors."""
        try:
            x = self.root.winfo_x()
            y = self.root.winfo_y()
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            # Check if at least part of the widget is on any monitor
            area = _get_cursor_monitor_workarea()
            if area is None:
                return False   # can't tell — assume OK
            # Also check against primary screen as a sanity bound
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            # Widget is offscreen if its right edge is < -w (way off left)
            # or its left edge is past all screens, or similarly for Y
            if x + w < -50 or x > sw + 500 or y + h < -50 or y > sh + 500:
                return True
        except Exception:
            pass
        return False

    def reset_position(self):
        """Move the widget back to the bottom-right of the primary monitor.
        Called from the tray icon or when the widget is detected offscreen."""
        try:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            self._anchor_x = sw - self._MARGIN_X
            self._anchor_y = sh - self._MARGIN_Y
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            self.root.geometry(f"{w}x{h}+{self._anchor_x - w}+{self._anchor_y - h}")
            self.root.deiconify()
            self._force_topmost()
            log.info("Widget position reset to primary monitor bottom-right")
        except Exception as e:
            log.error(f"Failed to reset widget position: {e}")

    def _force_topmost(self):
        """Re-assert always-on-top via Windows API — survives other windows stealing focus."""
        try:
            HWND_TOPMOST   = -1
            SWP_NOMOVE     = 0x0002
            SWP_NOSIZE     = 0x0001
            SWP_NOACTIVATE = 0x0010
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            ctypes.windll.user32.SetWindowPos(
                hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
            )
        except Exception:
            self.root.attributes("-topmost", True)   # fallback

    def _start_topmost_heartbeat(self):
        """Permanent 500 ms heartbeat: keeps the widget above everything
        AND follows the cursor's monitor (bottom-right corner anchoring).

        Wrapped in try/except so the heartbeat chain NEVER breaks — if it
        stops rescheduling, the widget becomes unreachable (no taskbar button).
        """
        try:
            self._force_topmost()
            self._anchor_to_monitor()
            # Auto-recover if the widget drifted offscreen (monitor disconnect,
            # resolution change, DPI switch, etc.)
            if self._is_offscreen():
                log.warning("Widget detected offscreen — resetting position")
                self.reset_position()
        except Exception as e:
            log.error(f"Heartbeat error (recovering): {e}")
        # ALWAYS reschedule — this line must never be skipped
        self.root.after(500, self._start_topmost_heartbeat)

    def _apply_state(self, state: str, hands_free_snap: bool = False):
        prev_state  = self._state
        self._state = state

        if self._anim_job:
            self.root.after_cancel(self._anim_job)
            self._anim_job = None

        # ── Always hide all inner children first; re-pack what this state needs ──
        for w in (self._canvas, self._btn_cancel, self._btn_stop):
            w.pack_forget()

        if state == "idle":
            self._inner.pack_forget()
            # Amber dot while correction-watch is armed — signals "press Enter to teach"
            idle_color = "#D4A060" if _correction_active else _IDLE_COLOR
            self._dot.config(bg=idle_color, fg=idle_color)
            self._dot.pack(fill="both", expand=True)
            self.root.config(bg=idle_color)
            self.root.attributes("-alpha", _IDLE_ALPHA)
            self.root.geometry(
                f"{_W_DOT}x{_H_DOT}"
                f"+{self._anchor_x - _W_DOT}+{self._anchor_y - _H_DOT}"
            )
        else:
            # Use the captured hands_free value (passed from set_state) so the
            # layout matches what was true at the moment of the call.
            hands_free_recording = (state == "recording" and hands_free_snap)
            w_outer = _W_WAVE_HF if hands_free_recording else _W_WAVE

            self._dot.pack_forget()
            border = _STATE_WAVE.get(state, ("", None, _BORDER_COLOR))[2]
            self._inner.pack(fill="both", expand=True, padx=_BORDER_PX, pady=_BORDER_PX)
            self.root.config(bg=border)
            self.root.attributes("-alpha", _ACTIVE_ALPHA)
            self.root.geometry(
                f"{w_outer}x{_H_WAVE}"
                f"+{self._anchor_x - w_outer}+{self._anchor_y - _H_WAVE}"
            )
            self._bar_h      = [0.08] * _N_BARS
            self._anim_phase = 0.0

            # ── Pack inner children based on state ───────────────────────────
            if hands_free_recording:
                # Full pill: ✕ | waveform | ⏺
                self._btn_cancel.pack(side="left",  fill="y")
                self._canvas.pack(    side="left",  fill="both", expand=True)
                self._btn_stop.pack(  side="right", fill="y")
            else:
                # Minimal: waveform only
                self._canvas.pack(side="left", fill="both", expand=True)

            if state == "loading":
                # Slow breathing pulse — model is loading in background
                self._anim_job = self.root.after(50, self._animate)
            elif state == "no_speech":
                ns_color = _STATE_WAVE["no_speech"][0]
                self._draw_bars([0.07 + 0.04 * math.sin(i * 1.3) for i in range(_N_BARS)],
                                ns_color)
                self._anim_job = self.root.after(1500, lambda: self._apply_state("idle"))
            elif state == "busy":
                wave, glow, _ = _STATE_WAVE["busy"]
                self._draw_bars([0.35 + 0.2 * math.sin(i * 0.9) for i in range(_N_BARS)],
                                wave, glow)
                self._anim_job = self.root.after(500, lambda: self._apply_state("idle"))
            else:
                self._anim_job = self.root.after(50, self._animate)

        # Sync tray icon colour
        if _tray:
            try:
                _tray.icon = _make_tray_image(_TRAY_COLORS.get(state, "#555555"))
            except Exception:
                pass

    def _animate(self):
        # Skip heavy canvas work when the widget is occluded or minimized
        if not self.root.winfo_viewable():
            self._anim_job = self.root.after(500, self._animate)
            return

        state = self._state

        if state == "recording":
            wave, glow, _ = _STATE_WAVE["recording"]
            level = 0.05
            try:
                if _audio_frames:
                    chunk = _audio_frames[-1].flatten()
                    level = float(np.sqrt(np.mean(chunk ** 2)))
                    level = min(1.0, level * 18)
            except Exception:
                pass
            level = max(0.05, level)
            for i in range(_N_BARS):
                centre = (i - (_N_BARS - 1) / 2) / ((_N_BARS - 1) / 2)
                env    = math.exp(-0.5 * centre ** 2)
                target = level * env * (0.65 + 0.35 * random.random())
                target = max(0.08, target)
                self._bar_h[i] = self._bar_h[i] * 0.55 + target * 0.45
            self._draw_bars(self._bar_h, wave, glow)

        elif state == "processing":
            wave, glow, _ = _STATE_WAVE["processing"]
            self._anim_phase += 0.25
            if self._anim_phase > 1000.0:
                self._anim_phase -= 1000.0
            for i in range(_N_BARS):
                phase = self._anim_phase + i * (2 * math.pi / _N_BARS)
                self._bar_h[i] = 0.12 + 0.55 * (math.sin(phase) * 0.5 + 0.5)
            self._draw_bars(self._bar_h, wave, glow)

        elif state == "done":
            wave, glow, _ = _STATE_WAVE["done"]
            self._draw_bars([0.9] * _N_BARS, wave, glow)
            _play_cue("done")
            self._anim_job = self.root.after(900, lambda: self._apply_state("idle"))
            return

        else:
            return

        self._anim_job = self.root.after(80, self._animate)

    def _draw_bars(self, heights, color, glow=None):
        """Draw a smooth filled waveform with an optional glow halo.

        Two layers when glow is given:
          1. Glow halo  — polygon scaled to 1.5× amplitude, filled with glow colour
          2. Core wave  — polygon at normal amplitude, filled with the main colour
        The result looks like a lit neon tube on a dark background.

        Uses cached canvas item IDs to update coordinates instead of
        delete-and-recreate on every frame (called every 80 ms).
        """
        c  = self._canvas
        cw = c.winfo_width()  or (_W_WAVE - 18)
        ch = c.winfo_height() or _H_WAVE

        n       = len(heights)
        cy      = ch / 2
        max_amp = max(1.0, (ch - 6) / 2)

        def _make_poly(scale: float):
            top, bot = [], []
            for i, h in enumerate(heights):
                x   = 2 + (i / max(n - 1, 1)) * (cw - 4)
                amp = max(0.05, h) * max_amp * scale
                top.append((x, cy - amp))
                bot.append((x, cy + amp))
            return [v for pt in top for v in pt] + [v for pt in reversed(bot) for v in pt]

        # Determine how many polygon layers we need (glow1, glow2, core)
        need_glow = glow is not None
        expected = 3 if need_glow else 1

        # Lazily create or reset cached item IDs
        if not hasattr(self, "_poly_ids") or len(self._poly_ids) != expected:
            c.delete("all")
            self._poly_ids = []
            if need_glow:
                self._poly_ids.append(c.create_polygon(0, 0, smooth=True, splinesteps=32, outline=""))
                self._poly_ids.append(c.create_polygon(0, 0, smooth=True, splinesteps=32, outline=""))
            self._poly_ids.append(c.create_polygon(0, 0, smooth=True, splinesteps=32, outline=""))

        idx = 0
        if need_glow:
            for scale, fill in ((1.5, glow), (1.15, glow)):
                pts = _make_poly(scale)
                if len(pts) >= 6:
                    c.coords(self._poly_ids[idx], *pts)
                    c.itemconfig(self._poly_ids[idx], fill=fill)
                idx += 1

        pts = _make_poly(1.0)
        if len(pts) >= 6:
            c.coords(self._poly_ids[idx], *pts)
            c.itemconfig(self._poly_ids[idx], fill=color)

    def _rebuild_menu(self):
        """Rebuild the right-click context menu.
        Called once at startup and again after a model switch so checkmarks update."""
        m = self._menu
        m.delete(0, "end")

        m.add_command(label="cait-whisper", state="disabled",
                      font=("Segoe UI", 10, "bold"))
        m.add_separator()

        # ── Switch Model cascade ──────────────────────────────────────────────
        switch_menu = tk.Menu(m, tearoff=0)

        moon_menu = tk.Menu(switch_menu, tearoff=0)
        for mdl in _MOONSHINE_MODELS:
            active = (_current_engine == "moonshine" and _current_model == mdl)
            lbl    = f"✓  {mdl}" if active else f"    {mdl}"
            moon_menu.add_command(
                label=lbl,
                command=lambda e="moonshine", mo=mdl: _switch_model(e, mo),
            )

        whis_menu = tk.Menu(switch_menu, tearoff=0)
        for mdl in _WHISPER_MODELS:
            active = (_current_engine == "whisper" and _current_model == mdl)
            lbl    = f"✓  {mdl}" if active else f"    {mdl}"
            whis_menu.add_command(
                label=lbl,
                command=lambda e="whisper", mo=mdl: _switch_model(e, mo),
            )

        para_menu = tk.Menu(switch_menu, tearoff=0)
        if not _nemo_available:
            para_menu.add_command(
                label="✗  NeMo not installed — re-run setup.bat",
                state="disabled", font=("Segoe UI", 8),
            )
            para_menu.add_command(
                label="    pip install nemo_toolkit[asr]  (Python 3.10/3.11 only)",
                state="disabled", font=("Segoe UI", 8),
            )
        para_menu.add_separator()
        for mdl in _PARAKEET_MODELS:
            active = (_current_engine == "parakeet" and _current_model == mdl)
            lbl    = f"✓  {mdl}" if active else f"    {mdl}"
            para_menu.add_command(
                label=lbl,
                state="normal" if _nemo_available else "disabled",
                command=lambda e="parakeet", mo=mdl: _switch_model(e, mo),
            )

        switch_menu.add_cascade(label="Moonshine",  menu=moon_menu)
        switch_menu.add_cascade(label="Whisper",    menu=whis_menu)
        para_label = "Parakeet ⚡" if _nemo_available else "Parakeet ⚡  (not installed)"
        switch_menu.add_cascade(label=para_label, menu=para_menu)
        m.add_cascade(label="Switch Model  ▸", menu=switch_menu)
        m.add_separator()

        # ── Audio cues submenu ────────────────────────────────────────────────
        cue_menu = tk.Menu(m, tearoff=0)
        for profile in ("subtle", "chime", "click", "scifi", "off"):
            active = (AUDIO_CUE == profile)
            lbl    = f"✓  {profile}" if active else f"    {profile}"
            cue_menu.add_command(
                label=lbl,
                command=lambda p=profile: _set_audio_cue(p),
            )
        cue_menu.add_separator()
        cue_menu.add_command(label="    ▶  Test start cue",
                             command=lambda: _play_cue("start", AUDIO_CUE if AUDIO_CUE != "off" else "subtle"))
        cue_menu.add_command(label="    ▶  Test done cue",
                             command=lambda: _play_cue("done",  AUDIO_CUE if AUDIO_CUE != "off" else "subtle"))
        m.add_cascade(label="Audio Cues  ▸", menu=cue_menu)
        m.add_separator()

        # ── History & Dictionary ──────────────────────────────────────────────
        m.add_command(label="History & Dictionary", command=_open_history_window)
        m.add_separator()

        # ── Spoken punctuation toggle ─────────────────────────────────────────
        m.add_command(
            label="Spoken Punct: ON" if _spoken_punct else "Spoken Punct: OFF",
            command=_toggle_spoken_punctuation,
        )

        # ── Auto-learn toggle ─────────────────────────────────────────────────
        m.add_command(
            label="Auto-Learn: ON" if _auto_learn_enabled else "Auto-Learn: OFF",
            command=_toggle_auto_learn,
        )

        # ── Mode toggle (PURE vs COMMAND) ─────────────────────────────────────
        m.add_command(
            label="Mode: COMMAND" if _command_mode else "Mode: PURE",
            command=_toggle_command_mode,
        )

        # ── Two-pass transcription toggle ─────────────────────────────────────
        m.add_command(
            label="Two-Pass: ON" if _two_pass_enabled else "Two-Pass: OFF",
            command=_toggle_two_pass,
        )

        # ── LLM cleanup toggle ────────────────────────────────────────────────
        m.add_command(
            label="LLM Cleanup: ON" if _post_process else "LLM Cleanup: OFF",
            command=self._toggle_llm,
        )
        m.add_separator()
        m.add_command(label="Reset Position", command=self.reset_position)
        m.add_command(label="Quit", command=_quit)

    def _show_menu(self, event):
        # Always rebuild so checkmarks and LLM label are current
        self._rebuild_menu()
        self._menu.tk_popup(event.x_root, event.y_root)
        # Stop the event propagating to parent widgets — without this, both
        # self._dot AND self.root fire _show_menu for the same click, the menu
        # opens twice in rapid succession and the first item-click gets eaten.
        return "break"

    def _toggle_llm(self):
        global _post_process
        _post_process = not _post_process
        _save_config_key("post_process", _post_process)
        log.info(f"LLM cleanup {'enabled' if _post_process else 'disabled'}")
        # entryconfig is a belt-and-suspenders update; _rebuild_menu on next open is the real fix
        self._menu.entryconfig(6, label="LLM Cleanup: ON" if _post_process else "LLM Cleanup: OFF")
        # Start / stop Ollama in the background so the UI stays responsive
        if _post_process:
            threading.Thread(target=_start_ollama_service, daemon=True, name="ollama-start").start()
        else:
            threading.Thread(target=_stop_ollama_service,  daemon=True, name="ollama-stop").start()

    def _drag_start(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _drag_move(self, event):
        x = self.root.winfo_x() + (event.x - self._drag_x)
        y = self.root.winfo_y() + (event.y - self._drag_y)
        self.root.geometry(f"+{x}+{y}")
        self._anchor_x = x + self.root.winfo_width()
        self._anchor_y = y + self.root.winfo_height()

    def _refresh_idle_color(self):
        """Re-apply idle dot colour based on current state.

        Priority (highest wins):
          1. correction watch armed  -> amber (#D4A060)
          2. COMMAND mode active     -> cool blue (#6E9CC9)
          3. default idle            -> configured _IDLE_COLOR
        """
        if self._state != "idle":
            return
        if _correction_active:
            color = "#D4A060"
        elif _command_mode:
            color = "#6E9CC9"
        else:
            color = _IDLE_COLOR
        self._dot.config(fg=color, bg=color)
        self.root.config(bg=color)

    def _show_ready_toast(self):
        """Briefly turn the idle dot green to signal the ASR model is loaded and ready."""
        if self._state != "idle":
            return
        self._dot.config(fg="#60D890", bg=_IDLE_COLOR)
        self.root.attributes("-alpha", 0.85)
        def _revert():
            try:
                self._dot.config(fg=_IDLE_COLOR, bg=_IDLE_COLOR)
                self.root.attributes("-alpha", _IDLE_ALPHA)
            except Exception:
                pass
        self.root.after(2000, _revert)

    def _notify_dict_learned(self, original: str, replacement: str):
        """Briefly flash a toast label on the widget when a dictionary entry is learned."""
        try:
            toast = tk.Label(
                self._inner,
                text=f"📖 '{original}' → '{replacement}'",
                bg="#1C2A1C", fg="#60D890",
                font=("Segoe UI", 8), padx=6, pady=2,
            )
            toast.place(relx=0.5, rely=0.5, anchor="center")
            self.root.after(2800, toast.destroy)
        except Exception:
            pass

    def _notify_bg_transcription(self, bg_text: str):
        """Toast that the background engine produced a better transcription.
        Stays visible a bit longer (4 seconds) because the user needs to
        decide whether to press Alt+Shift+Z to swap the pasted text."""
        try:
            preview = (bg_text[:40] + "…") if len(bg_text) > 40 else bg_text
            toast = tk.Label(
                self._inner,
                text=f"✨ Better version available · Alt+Shift+Z\n{preview}",
                bg="#1C1F2A", fg="#90B8E8",
                font=("Segoe UI", 8), padx=6, pady=2,
                justify="center",
            )
            toast.place(relx=0.5, rely=0.5, anchor="center")
            self.root.after(4000, toast.destroy)
        except Exception:
            pass


# ─── History & Dictionary window (separate process) ──────────────────────────

_history_proc = None   # subprocess.Popen — launched on demand

def _open_history_window():
    """Launch the history/dictionary window as a separate process.
    If it's already running, do nothing (the user can Alt-Tab to it).
    """
    global _history_proc
    if _history_proc and _history_proc.poll() is None:
        # Already running — nothing to do
        log.info("[HistoryWindow] already running (pid %d)", _history_proc.pid)
        return
    script = str(Path(__file__).parent / "history_window.py")
    _history_proc = subprocess.Popen(
        [sys.executable, script],
        cwd=str(Path(__file__).parent),
    )
    log.info("[HistoryWindow] launched as pid %d", _history_proc.pid)


# ─── Globals ──────────────────────────────────────────────────────────────────
_widget: StatusWidget = None
_tray   = None          # pystray.Icon — set in main()
_stream = None          # sd.InputStream — set in main()

_recording    = False
_processing   = False   # True while _transcribe_and_paste is running
# Max ~5 min of audio at 16 kHz, blocksize 1024 → ~4688 chunks (~19 MB).
# deque silently drops oldest frames if a hands-free session runs very long.
_MAX_AUDIO_CHUNKS = int(5 * 60 * SAMPLE_RATE / 1024)
_audio_frames: collections.deque = collections.deque(maxlen=_MAX_AUDIO_CHUNKS)
_record_lock  = threading.Lock()

_ctrl_down        = False
_win_down         = False
_space_down       = False
_alt_down         = False
_shift_down       = False
_hold_mode_active = False
_hands_free       = False

# Earliest time.time() at which a new recording is accepted.
# Set to now + 0.4 s after each paste so a stray Ctrl+Win can't fire immediately.
_ready_time: float = 0.0

# ─── Clean shutdown ───────────────────────────────────────────────────────────

def _quit(*_):
    """Tear everything down cleanly so the process actually exits.

    Must work when called from any thread (tkinter, pystray, keyboard).
    The key constraint: pystray's stop() posts WM_QUIT to its own message-loop
    thread asynchronously.  If we call os._exit() on the same thread before
    that message is processed, Shell_NotifyIcon(NIM_DELETE) never runs and the
    tray icon stays as a ghost.  Running the teardown in a fresh daemon thread
    lets both pystray and tkinter finish their own cleanup loops first.
    """
    log.info("Shutting down...")

    def _do_shutdown():
        # Double 'done' beep FIRST — before closing the audio device.
        try:
            _play_cue("done")
            time.sleep(0.40)
            _play_cue("done")
            time.sleep(0.40)
        except Exception:
            pass
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        try:
            if _stream:
                _stream.stop()
                _stream.close()
        except Exception:
            pass
        try:
            if _tray:
                _tray.visible = False
        except Exception:
            pass
        try:
            if _tray:
                _tray.stop()
        except Exception:
            pass
        try:
            if _history_proc and _history_proc.poll() is None:
                _history_proc.terminate()
                _history_proc.wait(timeout=2)
        except Exception:
            pass
        time.sleep(0.15)   # short grace for remaining threads
        os._exit(0)

    # Non-daemon so the beeps finish even if the main thread exits first.
    threading.Thread(target=_do_shutdown, daemon=False, name="shutdown").start()

    # Ask tkinter to exit its mainloop on its own thread
    try:
        if _widget:
            _widget.root.after(0, _widget.root.quit)
    except Exception:
        pass

# ─── Audio ────────────────────────────────────────────────────────────────────

def _audio_callback(indata, frames, time_info, status):
    if status:
        log.warning(f"Audio stream status: {status}")
    with _record_lock:
        if _recording:
            _audio_frames.append(indata.copy())

# ─── Transcribe + paste ───────────────────────────────────────────────────────

def _show_no_speech():
    """Show flat-bar waveform briefly to indicate no speech was detected."""
    if _widget:
        _widget.set_state("no_speech")


def _transcribe_and_paste(frames: list):
    global _processing
    try:
        if not frames:
            log.info("No audio captured — skipping")
            if _widget: _widget.set_state("idle")
            return

        audio = np.concatenate(frames, axis=0)
        audio_flat = audio.flatten().astype(np.float32)
        duration = len(audio_flat) / SAMPLE_RATE
        rms      = float(np.sqrt(np.mean(audio_flat ** 2)))
        log.info(f"Audio: {duration:.2f}s  RMS={rms:.4f}")

        if duration < MIN_RECORD_SECS:
            log.info(f"Recording too short ({duration:.2f}s < {MIN_RECORD_SECS}s) — skipping ASR")
            _show_no_speech()
            return

        if rms < 0.0005:
            log.info("Audio is silent (RMS below threshold) — skipping ASR")
            _show_no_speech()
            return

        t0 = time.perf_counter()
        raw_text = _run_asr(audio)
        t_asr = time.perf_counter()
        log.info(f"ASR ({t_asr - t0:.2f}s): {raw_text!r}")

        if not raw_text:
            log.info("Empty transcript — no speech detected in audio")
            _show_no_speech()
            return

        # ── Hallucination guard ───────────────────────────────────────────────
        # ASR models can produce repetitive garbage when audio is noisy or
        # unclear (e.g. "CaitOS Qwen Stellantis Fenekie" repeated dozens of
        # times).  Catch this with two checks:
        #   1. Words-per-minute: real speech tops out at ~250 wpm; hallucinations
        #      can produce 1000+ wpm worth of text for a 2-second clip.
        #   2. Phrase repetition: if any 2-4 word sequence makes up > 60% of the
        #      total word count, the output is almost certainly a loop.
        raw_words = raw_text.split()
        wpm = (len(raw_words) / max(duration, 0.1)) * 60
        if wpm > 400:
            log.warning(
                f"Hallucination detected: {len(raw_words)} words in {duration:.1f}s "
                f"= {wpm:.0f} wpm (max expected ~250) — discarding"
            )
            _show_no_speech()
            return
        if len(raw_words) >= 6:
            from collections import Counter
            for n in (2, 3, 4):
                ngrams = [" ".join(raw_words[i:i+n]) for i in range(len(raw_words)-n+1)]
                if ngrams:
                    top_count = Counter(ngrams).most_common(1)[0][1]
                    if top_count / len(ngrams) > 0.55:
                        log.warning(
                            f"Hallucination detected: {n}-gram repeated "
                            f"{top_count}/{len(ngrams)} times — discarding"
                        )
                        _show_no_speech()
                        return

        # ── Spoken punctuation ───────────────────────────────────────────
        # Replace spoken words ("period", "comma", "new line", …) with symbols
        # BEFORE LLM cleanup so the LLM sees clean punctuated text.
        punct_text = _apply_spoken_punctuation(raw_text)
        if punct_text != raw_text:
            log.info(f"Spoken punct: {punct_text!r}")
        final_text = punct_text

        # ── LLM cleanup (optional) ────────────────────────────────────────
        if _post_process:
            # Ollama is only started when the user explicitly toggles LLM Cleanup ON
            # via the menu (_toggle_llm).  We do NOT auto-start it here; if it isn't
            # running yet we skip cleanup and use the raw transcript.
            try:
                import ollama
                resp = ollama.chat(
                    model=OLLAMA_MODEL,
                    messages=[{"role": "user", "content": CLEANUP_PROMPT.format(transcript=raw_text)}],
                    options={"temperature": 0.1, "num_predict": 512},
                )
                final_text = resp["message"]["content"].strip()
                log.info(f"LLM ({time.perf_counter() - t_asr:.2f}s): {final_text!r}")
            except Exception as e:
                log.warning(f"LLM cleanup skipped (Ollama not ready — enable via menu): {e}")

        # ── Personal dictionary substitution ─────────────────────────────
        final_text = _apply_dictionary(final_text)
        if final_text != raw_text:
            log.info(f"Dictionary applied: {final_text!r}")

        # Declare once; used by both COMMAND mode branch and the normal paste path.
        global _last_transcription

        # ── COMMAND mode: classify & execute ─────────────────────────────
        # In PURE mode this block is skipped entirely (zero overhead).
        # In COMMAND mode the utterance is routed through a hybrid regex+LLM
        # classifier. Commands are executed directly; non-commands fall through
        # to the normal paste path as dictation.
        if _command_mode:
            try:
                import context as _ctx
                import commands as _cmds
                field_ctx = _ctx.get_field_context()
                cmd = _cmds.classify(final_text, has_selection=field_ctx.has_selection)
                if cmd is not None:
                    log.info(f"[Mode=COMMAND] classified as {cmd.type} (conf={cmd.confidence:.2f})")
                    # Save to history so the user can see what they said
                    _last_transcription = final_text
                    new_entry = {
                        "text":   f"[CMD:{cmd.type}] {final_text}",
                        "raw":    raw_text,
                        "ts":     datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "engine": f"{_current_engine}/{_current_model}",
                    }
                    threading.Thread(target=_save_history, args=(new_entry,),
                                     daemon=True, name="save-history").start()
                    # Execute; commands handle their own pasting/keyboard ops
                    ok = _cmds.execute(cmd, selection_text=field_ctx.selection, kb=keyboard)
                    if ok:
                        log.info(f"[Mode=COMMAND] ✓ executed ({time.perf_counter() - t0:.2f}s)")
                        if _widget:
                            _widget.set_state("done")
                        return
                    else:
                        log.warning(f"[Mode=COMMAND] execution failed; falling through to dictation")
            except Exception as e:
                log.warning(f"[Mode=COMMAND] classifier error; falling through to dictation: {e}")

        # ── Save to history ───────────────────────────────────────────────
        _last_transcription = final_text
        new_entry = {
            "text":   final_text,
            "raw":    raw_text,   # original ASR output before dictionary/LLM
            "ts":     datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "engine": f"{_current_engine}/{_current_model}",
        }
        threading.Thread(target=_save_history, args=(new_entry,),
                         daemon=True, name="save-history").start()

        # ── Paste ─────────────────────────────────────────────────────────
        pyperclip.copy(final_text)
        time.sleep(0.05)
        keyboard.send("ctrl+v")
        log.info(f"✓ Pasted ({time.perf_counter() - t0:.2f}s total)")

        # ── Arm correction watcher - waits for Enter to diff and learn ────
        # Pass final_text (what was actually pasted), not raw_text.
        # The user sees and edits final_text, so the diff must compare
        # against that - not the pre-dictionary ASR output.
        _start_correction_watch(final_text)

        # ── Two-pass: kick off higher-accuracy background transcription ──
        # Only makes sense when the primary engine is Moonshine (the fast one).
        # For Whisper or Parakeet, there's nothing to improve on.
        if _two_pass_enabled and _bg_asr_model is not None and _current_engine == "moonshine":
            threading.Thread(
                target=_run_bg_asr,
                args=(audio_flat, final_text),
                daemon=True,
                name="bg-asr",
            ).start()

        if _widget:
            _widget.set_state("done")   # auto-returns to idle after ~900 ms

    except Exception as e:
        log.error(f"Transcription error: {e}")
        if _widget: _widget.set_state("idle")

    finally:
        global _ready_time, _ctrl_down, _win_down, _hold_mode_active
        # keyboard.send("ctrl+v") fires synthetic key events through our hook
        # which can leave _ctrl_down stuck as True.  Hard-reset so the next
        # Ctrl+Win press is recognised cleanly.
        _ctrl_down = _win_down = _hold_mode_active = False
        # 400 ms grace period so an accidental immediate re-press is rejected
        # visually (busy flash) rather than silently swallowed.
        _ready_time = time.time() + 0.4
        _processing = False   # unlock last — ordering matters


def _cancel_recording():
    """Discard the current recording without transcribing (hands-free X button)."""
    global _recording, _hands_free, _hold_mode_active
    with _record_lock:
        if not _recording:
            return
        _recording = False
        _audio_frames.clear()
    _hands_free = False
    _hold_mode_active = False
    log.info("Recording cancelled")
    if _widget:
        _widget.set_state("idle")


def _start_recording():
    global _recording, _correction_active
    if _asr_model is None:
        log.info("Ignoring start — model still loading")
        if _widget: _widget.set_state("busy")
        return
    if _processing:
        log.info("Ignoring start — transcription in progress")
        if _widget: _widget.set_state("busy")
        return
    if time.time() < _ready_time:
        log.info("Ignoring start — cooldown active")
        if _widget: _widget.set_state("busy")
        return
    _correction_active = False   # cancel any pending correction watch
    if _widget:
        _ui_after(0, _widget._refresh_idle_color)
    with _record_lock:
        if _recording:
            return
        _audio_frames.clear()
        _recording = True
    log.info("● Recording")
    _play_cue("start")
    if _widget: _widget.set_state("recording")


def _stop_and_send():
    global _recording, _processing
    with _record_lock:
        if not _recording:
            return
        _recording = False
        frames = list(_audio_frames)
    _processing = True
    log.info("■ Stopped")
    if _widget: _widget.set_state("processing")
    threading.Thread(target=_transcribe_and_paste, args=(frames,), daemon=True).start()

# ─── Hotkey state machine ─────────────────────────────────────────────────────

_z_down = False   # tracks Z key for Alt+Shift+Z re-paste hotkey


def _repaste_last():
    """Re-paste the last transcription — Alt+Shift+Z."""
    global _last_transcription
    if not _last_transcription:
        log.info("Re-paste: nothing to paste yet")
        return
    if _recording or _processing:
        log.info("Re-paste blocked: recording/processing in progress")
        return
    log.info(f"Re-pasting: {_last_transcription!r}")
    pyperclip.copy(_last_transcription)
    # Release Alt and Shift so the OS sees a clean Ctrl+V, not Alt+Shift+Ctrl+V
    keyboard.release("alt")
    keyboard.release("shift")
    time.sleep(0.05)
    keyboard.send("ctrl+v")
    if _widget:
        _ui_after(0, lambda: _widget.set_state("done"))


_TRACKED_KEYS = frozenset({
    "ctrl", "left ctrl", "right ctrl",
    "alt", "left alt", "right alt",
    "shift", "left shift", "right shift",
    "enter", "z", "space",
    "windows", "left windows", "right windows",
})

def _on_key_event(event):
    global _ctrl_down, _win_down, _space_down, _alt_down, _shift_down, _z_down
    global _hold_mode_active, _hands_free
    key  = (event.name or "").lower()
    if key not in _TRACKED_KEYS:
        return   # skip irrelevant keys (letters, numbers, symbols, etc.)
    down = (event.event_type == "down")

    if key in ("ctrl", "left ctrl", "right ctrl"):
        _ctrl_down = down
    if key in ("alt", "left alt", "right alt"):
        _alt_down = down
    if key in ("shift", "left shift", "right shift"):
        _shift_down = down

    # ── Enter — trigger auto-dictionary correction check ─────────────────────
    if key == "enter" and down and _correction_active and not _recording:
        threading.Thread(target=_on_enter_correction, daemon=True,
                         name="correction-check").start()

    # ── Alt+Shift+Z — re-paste last transcription ─────────────────────────────
    if key == "z":
        _z_down = down
        if down and keyboard.is_pressed("alt") and keyboard.is_pressed("shift"):
            threading.Thread(target=_repaste_last, daemon=True, name="repaste").start()
            return

    # ── Space key — detects Ctrl+Win+Space without suppress=True ──────────────
    # Using add_hotkey(suppress=True) left the Win key stuck in Windows'
    # internal key-state table.  We instead track Space ourselves and fire
    # the hands-free toggle when all three are simultaneously held.
    # Both orderings are handled:
    #   Win-first → Win branch starts hold-mode, Space branch converts to hands-free
    #   Space-first → Win branch sees _space_down=True and goes hands-free directly
    if key == "space":
        if down and _ctrl_down and _win_down:
            _toggle_hands_free()
        _space_down = down

    if key in ("windows", "left windows", "right windows"):
        _win_down = down
        if down:
            if _hands_free:
                # Ctrl+Win pressed while hands-free → stop and transcribe
                _hands_free = False
                _stop_and_send()
            elif _ctrl_down and _space_down:
                # Space was already held → Ctrl+Win+Space (space-first ordering)
                _toggle_hands_free()
            elif _ctrl_down and not _hold_mode_active:
                # Ctrl+Win held → hold-to-talk
                _hold_mode_active = True
                _start_recording()
        else:
            if _hold_mode_active and not _hands_free:
                _hold_mode_active = False
                _stop_and_send()


def _toggle_hands_free():
    """Switch into or out of hands-free recording mode."""
    global _hands_free, _hold_mode_active
    if _hands_free:
        _hands_free = False
        _stop_and_send()
    else:
        _hold_mode_active = False
        _hands_free = True
        if _recording:
            # Already recording (e.g. was in hold-to-talk) — just refresh the
            # UI so the ✕/⏺ buttons appear.  _hands_free is already True so
            # set_state will capture hf=True and show the hands-free layout.
            if _widget:
                _widget.set_state("recording")
        else:
            _start_recording()
        log.info("Hands-free: talk freely, then Ctrl+Win to paste")

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    global _widget, _tray, _stream, _asr_model

    log.info("startup: loading history and dictionary")
    _load_history()
    _load_dictionary()

    # ── Widget first — appears immediately ────────────────────────────────────
    log.info("startup: creating widget")
    _widget = StatusWidget()
    _widget.set_state("loading")   # indigo pulse while model loads
    log.info("startup: widget visible")

    # ── System tray icon ──────────────────────────────────────────────────────
    log.info("startup: setting up tray icon")
    try:
        import pystray
        def _tray_model_label(item):
            return f"Model: {_current_engine} ({_current_model})"

        tray_menu = pystray.Menu(
            pystray.MenuItem("cait-whisper", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(_tray_model_label, None, enabled=False),
            pystray.MenuItem(
                "Switch Model",
                pystray.Menu(
                    # ── Moonshine ────────────────────────────────────────────
                    pystray.MenuItem("Moonshine", pystray.Menu(
                        *[
                            pystray.MenuItem(
                                (lambda m: lambda item: ("✓  " if (_current_engine == "moonshine" and _current_model == m) else "    ") + m)(mdl),
                                (lambda m: lambda item: _switch_model("moonshine", m))(mdl),
                            )
                            for mdl in _MOONSHINE_MODELS
                        ],
                    )),
                    # ── Whisper ──────────────────────────────────────────────
                    pystray.MenuItem("Whisper", pystray.Menu(
                        *[
                            pystray.MenuItem(
                                (lambda m: lambda item: ("✓  " if (_current_engine == "whisper" and _current_model == m) else "    ") + m)(mdl),
                                (lambda m: lambda item: _switch_model("whisper", m))(mdl),
                            )
                            for mdl in _WHISPER_MODELS
                        ],
                    )),
                    # ── Parakeet ─────────────────────────────────────────────
                    pystray.MenuItem(
                        "Parakeet ⚡" if _nemo_available else "Parakeet ⚡  (not installed)",
                        pystray.Menu(
                            *([] if _nemo_available else [
                                pystray.MenuItem("✗  Re-run setup.bat to install NeMo", None, enabled=False),
                                pystray.MenuItem("    (requires Python 3.10 or 3.11)", None, enabled=False),
                                pystray.Menu.SEPARATOR,
                            ]),
                            *[
                                pystray.MenuItem(
                                    (lambda m: lambda item: ("✓  " if (_current_engine == "parakeet" and _current_model == m) else "    ") + m)(mdl),
                                    (lambda m: lambda item: _switch_model("parakeet", m))(mdl),
                                    enabled=_nemo_available,
                                )
                                for mdl in _PARAKEET_MODELS
                            ],
                        ),
                    ),
                ),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "History & Dictionary",
                lambda item: _open_history_window(),
            ),
            pystray.MenuItem(
                lambda item: f"LLM Cleanup: {'ON' if _post_process else 'OFF'}",
                lambda: _widget.root.after(0, _widget._toggle_llm),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Show Widget",
                lambda item: _widget.root.after(0, _widget.reset_position),
            ),
            pystray.MenuItem("Quit", _quit),
        )
        _tray = pystray.Icon(
            "cait-whisper",
            icon=_make_tray_image(_TRAY_COLORS["idle"]),
            title="cait-whisper",
            menu=tray_menu,
        )
        _tray.run_detached()
        log.info("startup: tray icon OK")
    except Exception as e:
        # Tray is optional — log and continue without it
        log.warning(f"startup: tray icon unavailable ({e}), continuing without it")

    # ── Keyboard hooks ────────────────────────────────────────────────────────
    log.info("startup: registering keyboard hooks")
    try:
        keyboard.hook(_on_key_event)
        log.info("startup: keyboard hooks OK")
    except Exception as e:
        _fatal(f"Could not register keyboard hook: {e}\n\nMake sure you are running as Administrator.", e)

    # ── Mic stream ────────────────────────────────────────────────────────────
    log.info("startup: opening mic stream")
    try:
        _stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            callback=_audio_callback,
            blocksize=1024,
        )
        _stream.start()
        log.info("startup: mic stream OK")
    except Exception as e:
        _fatal(f"Could not open microphone: {e}\n\nCheck that a microphone is connected and not in use.", e)

    # ── Load ASR model in background — widget is already visible ─────────────
    def _load_model_bg():
        global _asr_model
        log.info("startup: loading ASR model (background)...")
        try:
            loaded = _load_asr()
            with _asr_lock:
                _asr_model = loaded
            log.info("startup: ASR model ready")
        except Exception as e:
            _ui_after(0, lambda: _fatal(f"Failed to load ASR model: {e}", e))
            return
        # Transition to idle and play the ready beeps — all on the main thread
        def _on_ready():
            _widget.set_state("idle")
            # Green flash on idle dot for 2 s — subtle "model is ready" signal
            _ui_after(100, _widget._show_ready_toast)
            def _beeps():
                _play_cue("done")
                time.sleep(0.35)
                _play_cue("done")
            threading.Thread(target=_beeps, daemon=True, name="startup-beep").start()
        _ui_after(0, _on_ready)

    threading.Thread(target=_load_model_bg, daemon=True, name="model-load").start()

    # ── Load background two-pass engine if enabled ────────────────────────────
    # Kicks off in its own daemon thread so the main UI is not blocked.
    # Silently no-ops when two-pass is disabled or the primary engine already
    # is a higher-accuracy model.
    threading.Thread(target=_load_bg_asr, daemon=True, name="bg-model-load").start()

    log.info("startup: entering main loop (model loading in background)")

    # ── Tkinter mainloop ──────────────────────────────────────────────────────
    try:
        _widget.root.mainloop()
    except KeyboardInterrupt:
        _quit()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _fatal(f"Unexpected error: {e}", e)
