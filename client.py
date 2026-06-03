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

# Brand tokens (palette, type, spacing, brand-mark drawing helpers).
# Imports cleanly with no Tk dependency; font resolution upgrades happen
# in main() after the Tk root exists.
import cw_paths
import splash as _splash_mod
import theme

# ─── Early crash handler ──────────────────────────────────────────────────────
# Runs before logging is configured, so we write directly to the log file
# and show a GUI dialog (no console when launched via pythonw).
_LOG_PATH_EARLY = cw_paths.app_dir() / "cait-whisper.log"

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
_LOG_PATH = cw_paths.app_dir() / "cait-whisper.log"
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
CONFIG_PATH = cw_paths.app_dir() / "config.json"

# Brand assets live in assets/. The .ico is generated on first launch if
# missing (theme.ensure_brand_ico is idempotent), so a fresh clone without
# the committed file still gets one. The history window points at the same
# path so taskbar/Alt-Tab/title bar all show the Φ-in-circle.
ASSETS_DIR = cw_paths.app_dir() / "assets"
ICO_PATH = ASSETS_DIR / "cait.ico"
try:
    ASSETS_DIR.mkdir(exist_ok=True)
    theme.ensure_brand_ico(ICO_PATH)
except Exception as _e:
    log.warning(f"[Theme] could not generate cait.ico: {_e}")

def load_config():
    if not CONFIG_PATH.exists():
        # First run: seed config.json from the bundled example. The frozen
        # download has no setup.bat to do this; from source it's a friendly
        # fallback if the user skipped setup.bat.
        example = cw_paths.resource_path("config.example.json")
        try:
            if example.exists():
                CONFIG_PATH.write_text(example.read_text(encoding="utf-8"),
                                       encoding="utf-8")
                log.info(f"config.json not found; seeded from {example}")
            else:
                _fatal("config.json not found and no config.example.json to "
                       "seed from. Please reinstall.")
        except Exception as e:
            _fatal(f"Could not create config.json: {e}", e)
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
# Input device: empty/None uses Windows default. Otherwise a substring match
# against device names (case-insensitive). Example: "Jabra" matches any
# device whose name contains "Jabra" - survives hostapi variations (WASAPI
# vs MME vs DirectSound exposing the same physical device multiple times).
INPUT_DEVICE   = cfg.get("input_device", "")
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

# Waveform style for the active recording strip. User-pickable from the
# right-click menu. Each style is a distinct visual rhythm for the same
# amplitude data. See StatusWidget._draw_wave_* methods for the renderers.
WAVEFORM_STYLES = (
    ("wave_filled",       "Wave (filled)"),
    ("bars_classic",      "Bars"),
    ("bars_mirror",       "Mirror bars"),
    ("dots",              "Dots"),
    ("line_oscilloscope", "Oscilloscope"),
    ("blocks_brutalist",  "Blocks"),
)
WAVEFORM_STYLE = cfg.get("waveform_style", "wave_filled")

# Spoken punctuation — replace words like "period" / "new line" with symbols.
# Toggled via right-click menu or config.json "spoken_punctuation": true/false.
_spoken_punct: bool = cfg.get("spoken_punctuation", True)
_auto_learn_enabled: bool = cfg.get("auto_learn", True)
_command_mode: bool = cfg.get("command_mode", False)  # COMMAND vs PURE mode
_one_shot_command: bool = False   # transient: set by Shift+Alt+C, consumed on next transcription
# v2.5.1 lean mode: retroactive buffer is opt-in. When OFF (default) the
# audio callback skips the deque append entirely, eliminating the constant
# memory write traffic for users who never press Shift+Alt+R.
_retro_enabled: bool = cfg.get("retro_enabled", False)
# Widget cursor-follow: when True (default), the dot follows you to whichever
# monitor your cursor moves to. v2.5.1 reworked this to compare monitor
# IDENTITY (HMONITOR handle) instead of coordinates, so transient post-wake
# work-area wobbles on a single monitor no longer move the dot.
_WIDGET_FOLLOW_CURSOR: bool = cfg.get("widget_follow_cursor", True)

# Widget placement: WHERE on the active monitor the dot rests. Composes with
# cursor-follow (it anchors at this position on whichever monitor the cursor
# is on). Manual drag overrides until the next placement pick or monitor hop.
#   bottom_center - modern dictation-app convention (Wispr Flow / superwhisper
#                   style); strip blooms symmetrically from center (default)
#   bottom_right  - traditional, tucked near the system tray
#   bottom_left   - mirror of bottom_right
WIDGET_PLACEMENTS = (
    ("bottom_center", "Bottom center"),
    ("bottom_right",  "Bottom right"),
    ("bottom_left",   "Bottom left"),
)
WIDGET_PLACEMENT: str = cfg.get("widget_placement", "bottom_center")

_use_screen_context: bool = cfg.get("use_screen_context", False)  # v2.3 OCR augmentation
_dev_logs: bool = cfg.get("dev_logs", False)  # v2.4 verbose debug logging

# Apply initial log level based on dev_logs setting.
# When dev_logs is ON, the root logger emits DEBUG; individual log.debug()
# calls throughout the code paint a full picture of what's happening.
if _dev_logs:
    logging.getLogger().setLevel(logging.DEBUG)
    log.info("[DevLogs] verbose logging enabled (DEBUG level)")

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
    """Persist multiple config values in a single read-write cycle.
    Secret-like keys (api_key, token, etc.) are redacted in log output."""
    try:
        with open(CONFIG_PATH) as f:
            data = json.load(f)
        data.update(updates)
        with open(CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=4)
        # Redact secrets before logging - matters once users put API keys in.
        try:
            from config_io import redact_for_log
            safe = redact_for_log(updates)
        except Exception:
            safe = updates
        for k, v in safe.items():
            log.info(f"Config saved: {k} = {v!r}")
    except Exception as e:
        # Also redact in the error log path
        try:
            from config_io import redact_for_log
            safe = redact_for_log(updates)
        except Exception:
            safe = updates
        log.error(f"FAILED to save config ({safe!r}): {e}")

# ─── History & Dictionary ─────────────────────────────────────────────────────

_HISTORY_PATH = cw_paths.app_dir() / "history.json"
_DICT_PATH    = cw_paths.app_dir() / "dictionary.json"
_MAX_HISTORY  = 50

_history:    list[dict] = []   # [{"text": "...", "ts": "2026-03-24 10:00", "engine": "whisper"}]
_dictionary: dict[str, str] = {}  # {"kate": "CAIT", "llm": "LLM", ...}
_last_transcription: str = ""   # used by Alt+Shift+Z re-paste

# ── Auto-dictionary correction state ─────────────────────────────────────────
_PENDING_PATH = cw_paths.app_dir() / "pending_corrections.json"
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


def _toggle_dev_logs():
    """Toggle verbose DEBUG-level logging for diagnostics.
    ON: every correction watch arm, clipboard probe, classifier decision,
    dictionary substitution, OCR call, etc. is logged.
    OFF: normal INFO-level logging (production default)."""
    global _dev_logs
    _dev_logs = not _dev_logs
    _save_config_key("dev_logs", _dev_logs)
    logging.getLogger().setLevel(logging.DEBUG if _dev_logs else logging.INFO)
    log.info(f"Dev logs {'enabled (DEBUG)' if _dev_logs else 'disabled (INFO)'}")
    if _widget:
        _widget.root.after(0, _widget._rebuild_menu)


def _toggle_screen_context():
    """Toggle screen-context OCR on/off and persist to config.
    When ON, the LLM command classifier receives OCR text from around the
    cursor as additional context. Fully local via RapidOCR. No-op in PURE
    mode. No-op if rapidocr-onnxruntime is not installed."""
    global _use_screen_context
    _use_screen_context = not _use_screen_context
    _save_config_key("use_screen_context", _use_screen_context)
    log.info(f"Screen-context {'enabled' if _use_screen_context else 'disabled'}")
    if _widget:
        _widget.root.after(0, _widget._rebuild_menu)


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


def _toggle_retro_buffer():
    """Toggle the rolling 20-second audio buffer for retroactive capture.
    Persists across restarts. When OFF the audio callback skips the deque
    append entirely - meaningful savings during long idle periods because
    the lock acquire + memcpy on every audio block adds up over time."""
    global _retro_enabled
    _retro_enabled = not _retro_enabled
    _save_config_key("retro_enabled", _retro_enabled)
    log.info(f"Retroactive buffer {'enabled' if _retro_enabled else 'disabled'}")
    if not _retro_enabled:
        # Empty the buffer to release memory immediately
        with _retro_lock:
            _retro_frames.clear()
    if _widget:
        _widget.root.after(0, _widget._rebuild_menu)


def _start_correction_watch(original_text: str):
    """Arm the correction watcher.  After paste, we remember the original
    transcription and wait for the user to press Enter, which signals
    they've finished editing.  The Enter handler then diffs and learns.

    While armed the idle dot turns amber so the user can see the app is
    ready to learn.  The watch auto-cancels after 30 s if Enter is never pressed."""
    global _correction_original, _correction_active, _correction_watch_cancel_id, _correction_debounce
    if not _auto_learn_enabled:
        log.debug("[AutoDict] watch NOT armed: auto-learn disabled")
        return
    _correction_original = original_text
    _correction_active = True
    # Defensive: make sure a stale debounce from a previous cycle can't
    # block the incoming Enter. The try/finally in _on_enter_correction
    # should already handle this, but resetting here costs nothing.
    _correction_debounce = False
    log.info("[AutoDict] watching for corrections (press Enter to commit)")
    log.debug(f"[AutoDict] armed with original_text={original_text!r} "
              f"(len={len(original_text)}, ts={time.time():.3f})")

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
        log.debug(f"[AutoDict] Enter ignored: active={_correction_active}, debounce={_correction_debounce}")
        return
    log.debug(f"[AutoDict] Enter handler fired (ts={time.time():.3f})")
    _correction_debounce = True
    _correction_active = False
    # Everything below runs inside try/finally so `_correction_debounce` is
    # GUARANTEED to reset even if a downstream call raises. This was a real
    # bug: a silent exception in _diff_and_learn or UI code left debounce=True
    # permanently, bricking auto-dictionary for the rest of the session.
    try:
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
            log.debug("[AutoDict] no original_text captured; nothing to diff against")
            return

        # Give the Enter keypress a moment to land before reading the clipboard
        time.sleep(0.15)

        try:
            clipboard_now = pyperclip.paste().strip()
            log.debug(f"[AutoDict] clipboard read: len={len(clipboard_now)}, "
                      f"matches_original={clipboard_now == original!s}")
        except Exception as e:
            log.debug(f"[AutoDict] clipboard read failed: {e}")
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
            log.debug("[AutoDict] clipboard unchanged; probing field via Ctrl+A/Ctrl+C")
            try:
                keyboard.send("ctrl+a")
                time.sleep(0.08)
                keyboard.send("ctrl+c")
                time.sleep(0.12)
                corrected = pyperclip.paste().strip()
                log.debug(f"[AutoDict] Ctrl+A/Ctrl+C grab: len={len(corrected)}")
                # Restore clipboard to what we originally pasted
                pyperclip.copy(original)
                log.info("[AutoDict] grabbed field content via Ctrl+A/Ctrl+C")
                # Guard: if the grabbed text is > 3× longer than the original,
                # Ctrl+A selected the whole document (email body, long note, etc.)
                # rather than just the pasted sentence — discard and bail out.
                if corrected and len(corrected.split()) > len(original.split()) * 3:
                    log.warning(f"[AutoDict] Ctrl+A grabbed too much context "
                                f"({len(corrected.split())} words vs {len(original.split())}) — skipping")
                    return
            except Exception as e:
                log.warning(f"[AutoDict] could not grab field content: {e}")
                return

        if not corrected or corrected == original:
            log.info("[AutoDict] no correction detected")
            log.debug(f"[AutoDict] corrected={corrected!r} original={original!r}")
            return

        log.debug(f"[AutoDict] diff inputs: original={original!r}, corrected={corrected!r}")
        try:
            _diff_and_learn(original, corrected)
        except Exception as e:
            log.warning(f"[AutoDict] diff_and_learn raised: {e}")
    finally:
        # ALWAYS release the debounce flag. Without this, a silent exception
        # bricks auto-dict for the rest of the session.
        _correction_debounce = False
        log.debug("[AutoDict] debounce released")


def _diff_and_learn(original: str, corrected: str):
    """Fuzzy word-level diff between original transcription and corrected text.
    Words that differ and sound similar are candidates for dictionary learning.
    Each candidate must be seen _CONFIDENCE_THRESHOLD times before promotion."""
    orig_words = original.split()
    corr_words = corrected.split()
    log.debug(f"[AutoDict] diff: {len(orig_words)} orig words, {len(corr_words)} corrected words")

    # Use SequenceMatcher for word-level alignment (handles insertions/deletions)
    sm = difflib.SequenceMatcher(None, orig_words, corr_words)
    candidates: list[tuple[str, str]] = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        log.debug(f"[AutoDict] opcode={tag} orig[{i1}:{i2}]={orig_words[i1:i2]} corr[{j1}:{j2}]={corr_words[j1:j2]}")
        if tag == "replace":
            # Pair up replaced words 1:1
            for ow, cw in zip(orig_words[i1:i2], corr_words[j1:j2]):
                ok = ow.lower().translate(_STRIP_PUNCT)
                ck = cw.lower().translate(_STRIP_PUNCT)
                if ok and ck and ok != ck:
                    candidates.append((ok, ck))
        # insert / delete — not a correction, skip

    log.debug(f"[AutoDict] {len(candidates)} candidate pair(s) before similarity gate")

    if not candidates:
        log.info("[AutoDict] diff found no word-level corrections")
        return

    pending = _load_pending_corrections()
    promoted = []

    for orig_w, corr_w in candidates:
        # Phonetic similarity gate — skip obviously unrelated words
        sim_ok = _words_sound_similar(orig_w, corr_w)
        log.debug(f"[AutoDict] similarity check '{orig_w}' vs '{corr_w}' -> {sim_ok}")
        if not sim_ok:
            log.info(f"[AutoDict] skipping '{orig_w}' → '{corr_w}' (not similar)")
            continue

        key = f"{orig_w}→{corr_w}"
        entry = pending.get(key, {"count": 0})
        entry["count"] += 1
        pending[key] = entry
        log.debug(f"[AutoDict] pending key {key!r} now count={entry['count']}")

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
            # Toast so the user sees that we're tracking this correction
            # and knows exactly how many more are needed.
            if _widget:
                _ui_after(0, _widget._notify_dict_pending,
                          orig_w, corr_w, entry["count"], _CONFIDENCE_THRESHOLD)

    _save_pending_corrections(pending)

    # Show toast for promoted entries
    if promoted and _widget:
        for orig_w, corr_w in promoted:
            _ui_after(0, _widget._notify_dict_learned, orig_w, corr_w)


# v2.5.1: split into system (rules) and user (content). System role
# carries the format constraint ("ONLY the cleaned text") - models comply
# more reliably when this is in the system message than buried in user text.
CLEANUP_SYSTEM_PROMPT = """You are a dictation post-processor. Clean up raw speech transcripts:
- Remove filler words (um, uh, like, you know, basically, so)
- Fix grammar and sentence structure naturally
- Add proper punctuation
- Preserve the speaker's meaning and tone exactly
- Output ONLY the cleaned text, no preamble, no commentary."""

CLEANUP_USER_TEMPLATE = "Raw transcript:\n{transcript}"

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

    # Hard cap on the dictionary hint. Whisper can latch onto long
    # initial_prompts and echo them back in long outputs, producing loops
    # like "CaitOS qwen Stellantis Fenekie ..." repeated many times.
    # 12 words is enough to bias recognition without dominating the prompt.
    _MAX_HINT_WORDS = 12

    def transcribe(self, audio_1d: np.ndarray) -> str:
        audio = audio_1d.astype(np.float32)
        # Build initial_prompt from a small, capped slice of dictionary values
        if _dictionary:
            hint_words = list(_dictionary.values())[: self._MAX_HINT_WORDS]
            hint = " ".join(hint_words)
        else:
            hint = None
        segments, _info = self._model.transcribe(
            audio,
            language=LANGUAGE,
            vad_filter=True,
            beam_size=1,
            temperature=0,
            condition_on_previous_text=False,
            initial_prompt=hint,
            # v2.5.1: skip timestamp computation. We don't surface word/segment
            # timing anywhere in the app, so this is a free 10-20% speedup.
            without_timestamps=True,
        )
        # v2.5.1: filter out segments the model itself thinks are silence.
        # `no_speech_prob` is Whisper's own indicator. When >0.85 the segment
        # is almost certainly a hallucination from background noise / fan / hum.
        # SAFETY: if filtering would drop ALL segments, keep them all - we
        # never want to return empty when Whisper actually transcribed something.
        # The user is waiting for output; a slightly-noisy transcription beats
        # a silent failure that looks like the app is broken.
        all_segs = list(segments)
        kept = []
        for seg in all_segs:
            nsp = getattr(seg, "no_speech_prob", 0.0)
            if nsp > 0.85:
                log.debug(f"[Whisper] dropping segment with no_speech_prob={nsp:.2f}: {seg.text!r}")
                continue
            kept.append(seg.text)
        if not kept and all_segs:
            log.warning("[Whisper] all segments scored as silence by no_speech_prob; "
                        "keeping them anyway rather than returning empty")
            kept = [seg.text for seg in all_segs]
        return " ".join(kept).strip()


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
    """Flatten audio to 1-D float32 and dispatch to the active engine.
    v2.5.1: if the model was idle-unloaded, reload it transparently before
    transcribing. Marks the last-use timestamp so the idle supervisor knows
    when to unload again."""
    global _asr_model, _last_asr_use_time
    # If the model was unloaded by the idle supervisor, reload now.
    # Holds the lock during reload so a concurrent _switch_model can't race.
    with _asr_lock:
        if _asr_model is None:
            log.info("[IdleUnload] ASR model was unloaded - reloading now (1-3 sec delay)")
            try:
                _asr_model = _load_asr()
                log.info(f"[IdleUnload] reload OK: {_current_engine}/{_current_model}")
            except Exception as e:
                log.error(f"[IdleUnload] reload failed: {e}")
                return ""
        _last_asr_use_time = time.time()
        return _asr_model.transcribe(audio.flatten().astype(np.float32))


# v2.5.1 idle-unload state
# Timestamps tracking when each model was last used. The supervisor thread
# polls these every 60s and drops the model if the idle threshold is exceeded.
# `0.0` means "never used in this session" - supervisor leaves it loaded.
_last_asr_use_time: float = 0.0
_last_bg_asr_use_time: float = 0.0
_ASR_IDLE_UNLOAD_SECS = 10 * 60   # 10 minutes
_BG_IDLE_UNLOAD_SECS  = 5 * 60    # 5 minutes


def _idle_unload_supervisor():
    """Daemon thread: every 60 seconds, check if ASR models have been idle
    past their thresholds and drop their references if so. Reload happens
    transparently on the next _run_asr() / _run_bg_asr() call.

    Safe to run continuously - the locks make it race-free with active
    transcriptions and model-switch operations."""
    global _asr_model, _bg_asr_model
    log.info(f"[IdleUnload] supervisor started (primary={_ASR_IDLE_UNLOAD_SECS}s, "
             f"bg={_BG_IDLE_UNLOAD_SECS}s)")
    while True:
        try:
            time.sleep(60)
            now = time.time()
            # Don't unload while a recording or transcription is in progress
            if _recording or _processing:
                continue
            # Primary engine
            if (_asr_model is not None
                    and _last_asr_use_time > 0
                    and (now - _last_asr_use_time) > _ASR_IDLE_UNLOAD_SECS):
                with _asr_lock:
                    # Re-check inside lock in case _switch_model touched it
                    if _asr_model is not None:
                        log.info(f"[IdleUnload] primary ASR idle "
                                 f"{(now - _last_asr_use_time)/60:.1f} min - unloading")
                        _asr_model = None
            # Background engine (two-pass)
            if (_bg_asr_model is not None
                    and _last_bg_asr_use_time > 0
                    and (now - _last_bg_asr_use_time) > _BG_IDLE_UNLOAD_SECS):
                with _bg_asr_lock:
                    if _bg_asr_model is not None:
                        log.info(f"[IdleUnload] background ASR idle "
                                 f"{(now - _last_bg_asr_use_time)/60:.1f} min - unloading")
                        _bg_asr_model = None
        except Exception as e:
            log.warning(f"[IdleUnload] supervisor error (continuing): {e}")


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
    # Idempotency: if the model is already loaded, don't waste memory loading
    # a second instance. Important now that this function is called from
    # multiple paths (startup, toggle, post-idle reload).
    if _bg_asr_model is not None:
        log.debug("[TwoPass] bg engine already loaded; skipping reload")
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
    after the main paste has already happened, so we are never on the hot path.

    v2.5.1: if the bg engine was idle-unloaded, reload it before transcribing.
    We're already off the hot path so a reload delay here is invisible to the
    user - they got their fast Moonshine paste seconds ago."""
    global _bg_asr_model, _last_bg_asr_use_time
    if not _two_pass_enabled:
        return
    try:
        # Reload if needed (the idle supervisor may have dropped it)
        if _bg_asr_model is None:
            log.info("[TwoPass] bg engine was unloaded - reloading")
            _load_bg_asr()
            if _bg_asr_model is None:
                # Load failed; give up silently
                return
        with _bg_asr_lock:
            if _bg_asr_model is None:
                return
            t0 = time.perf_counter()
            bg_text = _bg_asr_model.transcribe(audio_flat).strip()
            _last_bg_asr_use_time = time.time()
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


def _set_waveform_style(style: str):
    """Switch the recording-strip waveform renderer and persist to config.
    The change applies on the next animation frame, so the next time the
    user records they see the chosen style."""
    global WAVEFORM_STYLE
    WAVEFORM_STYLE = style
    _save_config_key("waveform_style", style)
    log.info(f"Waveform style set to: {style}")
    if _widget:
        # Clear any cached canvas items so the next draw starts fresh.
        try:
            _widget._canvas.delete("all")
            _widget._wave_items = None
        except Exception:
            pass
        _widget.root.after(0, _widget._rebuild_menu)


def _set_widget_placement(placement: str):
    """Switch where the dot rests on its monitor and persist to config.
    Clears any manual drag placement and the saved position, then re-anchors
    immediately so the change is visible without a restart."""
    global WIDGET_PLACEMENT
    WIDGET_PLACEMENT = placement
    _save_config_key("widget_placement", placement)
    log.info(f"Widget placement set to: {placement}")
    if _widget:
        def _apply():
            # Drop the manual-placement override + saved position so the
            # preset takes over, then re-anchor to the new spot.
            _widget._user_placed = False
            _widget._anchored_hmon = None   # force re-anchor on next heartbeat too
            try:
                with open(CONFIG_PATH) as f:
                    data = json.load(f)
                if "widget_position" in data:
                    data.pop("widget_position", None)
                    with open(CONFIG_PATH, "w") as f:
                        json.dump(data, f, indent=4)
            except Exception:
                pass
            _widget._reanchor_current_monitor()
            _widget._rebuild_menu()
        _widget.root.after(0, _apply)


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
            # Audible confirmation so the user knows the swap completed
            # (same "done" cue as transcription-ready). Runs on a daemon
            # thread so we don't block the model-swap thread on audio IO.
            threading.Thread(
                target=lambda: _play_cue("done"),
                daemon=True,
                name="switch-cue",
            ).start()
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
    info = _get_cursor_monitor_info()
    return info[1] if info else None


def _get_cursor_monitor_info():
    """Return (hmon_handle, (x, y, w, h)) for the cursor's monitor, or None.
    Exposing the HMONITOR handle lets callers compare monitor identity
    instead of just coordinates - critical for avoiding spurious "monitor
    changed" detections when only the work-area dimensions wobble (taskbar
    autohide toggling, DPI re-init after sleep/wake, etc.)."""
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
            return hmon, (left, top, right - left, bottom - top)
    except Exception:
        pass
    return None


def _get_monitor_bounds_for_point(px: int, py: int, *, work_area: bool = True):
    """Return the bounds (x, y, w, h) of the monitor that contains the
    screen point (px, py). Falls back to None if the Win32 call fails.

    This is the point-based sibling of _get_cursor_monitor_info. Used to
    confine a popup (the hover card) to the SAME physical monitor as the
    widget so it can never spill across the bezel onto a neighbouring
    monitor when the widget sits near a screen edge.

    Args:
        px, py: absolute screen coordinates of a point on the target monitor
        work_area: True returns rcWork (excludes the taskbar); False returns
            rcMonitor (the full physical monitor rectangle).
    """
    try:
        pt = _POINT()
        pt.x = int(px)
        pt.y = int(py)
        hmon = ctypes.windll.user32.MonitorFromPoint(pt, 2)  # NEAREST
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            left, top, right, bottom = mi.rcWork if work_area else mi.rcMonitor
            return left, top, right - left, bottom - top
    except Exception:
        pass
    return None


# ─── Tray icon helpers ────────────────────────────────────────────────────────

_tray_icon_cache: dict[str, Image.Image] = {}

def _make_tray_image(color: str) -> Image.Image:
    """Tray icon: brand Φ-in-circle in the per-state color.
    v2.5.3: was a flat filled disc; now uses theme.render_mark_image so the
    tray reads as the same brand mark the user sees in the widget and the
    history window, just tinted to reflect state."""
    cached = _tray_icon_cache.get(color)
    if cached is not None:
        return cached
    # All-one-color mark: ring + Φ both painted in `color`, no inner fill.
    # The result is a tinted Φ-in-circle silhouette that scales cleanly to
    # any tray-icon size Windows asks for.
    img = theme.render_mark_image(
        64, border_color=color, glyph_color=color, fill_color=None,
    )
    _tray_icon_cache[color] = img
    return img

# Tray icon dot color per state. Brand-aligned so the icon in the system tray
# tells the same story as the floating widget mark.
_TRAY_COLORS = {
    "idle":       theme.INK_MUTE,    # quiet, low-attention
    "loading":    theme.INFO,        # cool blue — "waking up"
    "recording":  theme.CORAL,       # primary brand action
    "processing": theme.MUSTARD,     # jewelry — "thinking"
    "done":       theme.CORAL_SOFT,  # success flash (brand-aligned, not green)
    "no_speech":  theme.INK_FAINT,   # barely there
}

# Per-state waveform colours: (wave_color, glow_color, border_color)
# v2.5.4: border color is now INK_MUTE for EVERY state. State change is
# signaled by the waveform color itself (coral/mustard/etc), so the border
# doesn't also need to communicate state. INK_MUTE is the standard brand
# border color used everywhere a container needs an outline.
#
# Brand border standard:
#   theme.BORDER_MED  (2px, INK_MUTE) - floating containers, recording strip,
#                                       hover card outline
#   theme.BORDER_THIN (1px, INK_MUTE) - inline dividers between sections
# v2.5.6: processing moved MUSTARD -> CORAL_SOFT. Mustard is the brand's
# reserved "correction-watch" jewelry (the idle pulse) - reusing it for
# processing diluted that meaning and broke the coral-family seamlessness of
# the record -> process -> done flow. Now the whole flow stays in the coral
# family (CORAL recording, CORAL_SOFT processing + done) and the STATES are
# distinguished by MOTION, not hue. 'busy' keeps mustard because it's a true
# "not ready, wait" warning outside the normal flow.
_STATE_WAVE = {
    # v2.5.6: loading moved INFO (cool blue) -> CORAL_SOFT so the STARTUP
    # waveform is on-brand. The whole lifecycle now lives in the coral family;
    # only full-saturation CORAL is reserved for live recording (the "you're
    # the star, talk" moment) while CORAL_SOFT carries the supporting states
    # (warming up, processing, done).
    "loading":    (theme.CORAL_SOFT,  theme.INK_SOFT, theme.INK_MUTE),
    "recording":  (theme.CORAL,       theme.INK_SOFT, theme.INK_MUTE),
    "processing": (theme.CORAL_SOFT,  theme.INK_SOFT, theme.INK_MUTE),
    "done":       (theme.CORAL_SOFT,  theme.INK_SOFT, theme.INK_MUTE),
    "no_speech":  (theme.INK_FAINT,   None,           theme.INK_MUTE),
    "busy":       (theme.MUSTARD,     theme.INK_SOFT, theme.INK_MUTE),
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

# v2.5.6: heights matched to the resting coin (32px) so the idle->record
# transition is a SEAMLESS horizontal expansion with no vertical jump. Equal
# heights mean coin and strip occupy the same vertical band; the strip just
# extends leftward. Combined with pill-shaped end-caps (SetWindowRgn, see
# _apply_window_region), the strip's 16px-radius right cap is identical to
# the 32px coin sharing the same anchor corner, so the coin visually
# stretches into the strip.
_W_WAVE,    _H_WAVE = 168, 32   # hold-to-talk: waveform only
_W_WAVE_HF, _H_WAVE = 240, 32   # hands-free:  ✕ + waveform + Φ
_N_BARS  = 15
_BAR_W   = 4
_BAR_GAP = 2

# ── Appearance — driven by config.json "appearance" section ───────────────────
_ap = cfg.get("appearance", {})

# Recording strip chrome. INK = brand primary dark surface so the strip
# matches the rest of the brand. Border CORAL overridden per-state via
# _STATE_WAVE for active states.
_BG_ACTIVE    = theme.INK
_BORDER_COLOR = theme.CORAL
_BORDER_PX    = int(_ap.get("active_border_px",  2))
_ACTIVE_ALPHA = float(_ap.get("active_alpha",    0.95))

_IDLE_COLOR   = theme.CORAL   # unused now; mark colors come from theme tokens
_IDLE_ALPHA   = float(_ap.get("idle_alpha", 0.45))
# v2.5.6: 32px to match the recording strip height EXACTLY. Equal heights
# make idle->record a pure horizontal expansion (no vertical jump), and a
# 32px circle == the strip's 16px-radius pill cap, so the coin appears to
# stretch into the strip. Config 'idle_size' can still override.
_W_DOT = _H_DOT = int(_ap.get("idle_size", 32))

# Windows-only "transparent color" trick: any pixel rendered in this exact
# RGB on a Toplevel becomes 100% transparent on screen. We use a magenta
# that the brand palette never produces, so nothing legitimate disappears.
# This is what lets the widget mark appear as a floating circle with no
# visible square Canvas backdrop, while staying fully opaque (no fuzzy alpha).
_TRANSPARENT_KEY = "#ff00ff"


class StatusWidget:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)
        # v2.5.5: -transparentcolor is no longer used. It was unreliable
        # across display drivers / color profiles - magenta would leak
        # through as visible pink corners on some setups. Instead, the
        # widget is now a small dark INK badge with DWM-rounded corners
        # (squircle on Win11). The brand mark sits inside; the badge area
        # outside the mark visually fades into dark desktops.
        self.root.configure(bg=theme.INK)

        # Hide from taskbar AND Alt-Tab. The widget lives in the system
        # tray and floats over the desktop - it is NOT an app entry. The
        # -toolwindow attribute sets WS_EX_TOOLWINDOW at the Win32 level,
        # which is the standard way to tell Windows "this is a floating
        # utility surface, not a window to be listed alongside Word/Chrome".
        # The history window does NOT get this treatment - it's a real
        # window the user opens and switches to.
        try:
            self.root.attributes("-toolwindow", True)
        except Exception:
            pass

        # Initial anchor: primary monitor work-area (excludes taskbar) +
        # placement. The first heartbeat re-anchors to the cursor's monitor,
        # but computing a correct work-area position here avoids a brief
        # flash behind the taskbar at startup.
        _prim = _get_monitor_bounds_for_point(0, 0, work_area=True)
        if _prim:
            _mx, _my, _mw, _mh = _prim
        else:
            _mx, _my = 0, 0
            _mw = self.root.winfo_screenwidth()
            _mh = self.root.winfo_screenheight()
        self._anchor_x = self._placement_anchor_x(_mx, _mw)
        self._anchor_y = _my + _mh - self._MARGIN_Y
        # Respect a user-dragged position from a previous session, if any.
        # Heartbeat's auto-anchor-to-cursor-monitor will skip while _user_placed
        # is True, so the widget stays exactly where the user put it.
        #
        # Bounds check: positions saved under v2.4 (DPI-unaware coordinate
        # system) may now land off-screen with v2.5's per-monitor DPI
        # awareness. Validate against virtual-screen bounds; fall back to
        # auto-anchor if the saved coords are outside any monitor.
        self._user_placed = False
        # Track which physical monitor the dot is anchored to. Initialized
        # by the first heartbeat call to _anchor_to_monitor. Used to suppress
        # spurious re-anchors when the same monitor's work-area dimensions
        # change (taskbar / DPI / wake) - we only move if the monitor IDENTITY
        # (HMONITOR handle) changes.
        self._anchored_hmon = None
        # Strike counter for the offscreen-rescue debounce (3 consecutive
        # offscreen heartbeats required before reset_position fires).
        self._offscreen_strike_count = 0
        saved_pos = cfg.get("widget_position")
        if isinstance(saved_pos, dict) and "x" in saved_pos and "y" in saved_pos:
            try:
                px = int(saved_pos["x"])
                py = int(saved_pos["y"])
                # Get virtual-screen bounds (covers all monitors).
                gm = ctypes.windll.user32.GetSystemMetrics
                vx, vy = gm(76), gm(77)            # SM_X/YVIRTUALSCREEN
                vw, vh = gm(78), gm(79)            # SM_CX/CYVIRTUALSCREEN
                # Allow a 50-pixel tolerance: anchor is bottom-right corner
                # so it can sit a bit past virtual bounds and still be visible
                in_bounds = (
                    vx - 50 <= px <= vx + vw + 50
                    and vy - 50 <= py <= vy + vh + 50
                )
                if in_bounds:
                    self._anchor_x = px
                    self._anchor_y = py
                    self._user_placed = True
                    log.info(f"Widget: restored saved position ({self._anchor_x}, {self._anchor_y})")
                else:
                    log.info(f"Widget: saved position ({px}, {py}) outside virtual screen "
                             f"({vx},{vy} {vw}x{vh}) — falling back to auto-anchor")
            except Exception as e:
                log.debug(f"Widget: position load failed ({e}); auto-anchoring")

        # Brand mark: Φ inside a coral circle. Replaces the simple filled
        # dot from v2.4. Drawn on a Canvas so we can compose ring + glyph
        # in any state colour. State-painting code calls _redraw_mark(...)
        # instead of self._dot.config(text=, fg=) - functional API.
        self._dot = tk.Canvas(
            self.root,
            width=_W_DOT, height=_H_DOT,
            bg=_IDLE_COLOR, highlightthickness=0,
            borderwidth=0,
        )

        # Inner frame — sits 1 px inside the root window so the root bg
        # shows through as a thin border in active states
        self._inner = tk.Frame(self.root, bg=_BG_ACTIVE)

        # Waveform canvas (lives inside _inner; packed dynamically per state)
        self._canvas = tk.Canvas(self._inner, width=_W_WAVE - 2 * _BORDER_PX,
                                 height=_H_WAVE, bg=theme.INK, highlightthickness=0)

        # ── Hands-free side buttons ─────────────────────────────────────────
        # Both buttons are rendered as PIL-rasterized brand glyphs displayed
        # in identical-sized tk.Labels. Same widget type, same rendering
        # pipeline, same bounding box -> automatic optical alignment with
        # the waveform's vertical center. Hover states swap the PhotoImage
        # to a different color rather than re-rendering or changing fg.
        #
        # Glyph dimensions: 18×18 px inside a Label padded 10px horizontal.
        # Total button width ~38px each, leaving ~164px for the waveform
        # in a 240px strip.
        _BTN_GLYPH_PX  = 18
        _BTN_PAD_X     = 10

        # Pre-cache all four photos (cancel resting/hover, submit resting/
        # hover). theme.get_glyph_photo caches by (name, size, color) so
        # repeat calls are free.
        self._btn_cancel_rest = theme.get_glyph_photo("close", _BTN_GLYPH_PX, theme.INK_FAINT)
        self._btn_cancel_hov  = theme.get_glyph_photo("close", _BTN_GLYPH_PX, theme.PAPER)
        self._btn_stop_rest   = theme.get_glyph_photo("phi",   _BTN_GLYPH_PX, theme.CORAL)
        self._btn_stop_hov    = theme.get_glyph_photo("phi",   _BTN_GLYPH_PX, theme.CORAL_SOFT)

        # Left: cancel/discard. Custom close glyph, INK_FAINT resting,
        # PAPER on hover. Quiet so it doesn't compete with the submit
        # action, but legible.
        self._btn_cancel = tk.Label(
            self._inner, image=self._btn_cancel_rest,
            bg=theme.INK, cursor="hand2",
            padx=_BTN_PAD_X, pady=0, borderwidth=0, highlightthickness=0,
        )
        self._btn_cancel.bind("<ButtonRelease-1>", lambda e: _cancel_recording())
        self._btn_cancel.bind(
            "<Enter>", lambda e: self._btn_cancel.config(image=self._btn_cancel_hov)
        )
        self._btn_cancel.bind(
            "<Leave>", lambda e: self._btn_cancel.config(image=self._btn_cancel_rest)
        )

        # Right: stop + send. Brand Φ rendered via the same PIL pipeline
        # as the close glyph, so the two icons share AA quality and visual
        # weight. CORAL resting, CORAL_SOFT on hover (standard brand hover).
        self._btn_stop = tk.Label(
            self._inner, image=self._btn_stop_rest,
            bg=theme.INK, cursor="hand2",
            padx=_BTN_PAD_X, pady=0, borderwidth=0, highlightthickness=0,
        )
        self._btn_stop.bind("<ButtonRelease-1>", lambda e: _stop_and_send())
        self._btn_stop.bind(
            "<Enter>", lambda e: self._btn_stop.config(image=self._btn_stop_hov)
        )
        self._btn_stop.bind(
            "<Leave>", lambda e: self._btn_stop.config(image=self._btn_stop_rest)
        )

        # Right-click context menu - built (and rebuilt after model switches)
        # by _rebuild_menu(). Brand-styled via _styled_menu so colors match
        # the rest of the app instead of falling back to Windows defaults.
        self._menu = self._styled_menu(self.root)
        self._rebuild_menu()

        for w in (self.root, self._dot, self._inner, self._canvas,
                  self._btn_cancel, self._btn_stop):
            w.bind("<ButtonPress-3>", self._show_menu)
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>",     self._drag_move)
            # Hover card: show after a short delay, hide when the cursor
            # leaves both widget and card. Bound to the root and dot so
            # the card doesn't appear mid-drag or during waveform display.
            w.bind("<Enter>", self._on_widget_hover)
            w.bind("<Leave>", self._on_widget_leave)

        # Hover card state
        self._hover_card = None
        self._hover_show_job = None
        self._hover_hide_job = None

        self._anim_job   = None
        self._bar_h        = [0.08] * _N_BARS   # smoothed bar heights 0..1
        self._anim_phase   = 0.0
        self._state        = "idle"

        self.root.protocol("WM_DELETE_WINDOW", _quit)
        self._apply_state("idle")

        # Apply Windows 11 DWM rounded corners (fallback if SetWindowRgn fails)
        self.root.update()
        self._apply_dwm_round_corners()
        # Guarantee the initial coin is clipped to a circle. The first
        # _apply_state("idle") above may have run before the window was fully
        # realized (winfo_width could read 1), so re-apply now that update()
        # has materialized the window at its real size.
        self._apply_window_region("circle")

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
        """Request Windows 11 DWM rounded corners. Silent no-op on Windows 10.

        Note: when a custom window region is set (see _apply_window_region),
        Windows applies the REGION shape and ignores DWM corner rounding.
        So this only takes effect as a fallback if SetWindowRgn fails - in
        which case a DWM-rounded rectangle is a nicer degraded look than a
        hard-edged box."""
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

    def _apply_window_region(self, shape: str):
        """Clip the widget window to a non-rectangular SHAPE via SetWindowRgn.

        This is true geometric clipping at the Win32 level: genuinely
        transparent outside the shape, with none of the color-key bleed that
        plagued the old -transparentcolor approach (which we removed in
        v2.5.5 after magenta corners leaked on some display setups).

        The trade-off is a 1-bit (aliased) clip edge, but it is effectively
        invisible here:
          - idle coin: the coral ring is inset ~12% inside the clip circle,
            so the aliased boundary falls in transparent margin. Only the
            dark INK fill's circular edge is aliased - dark-on-desktop, the
            least noticeable case.
          - recording strip: the waveform and side glyphs are inset well
            clear of the pill caps (a centered gaussian waveform keeps the
            edge bars short), so only the INK pill outline is aliased.

        MUST be re-applied on every SIZE change: the region is defined in
        window pixel coordinates, so a stale 32x32 circle would clip a
        resized 240x32 strip down to a tiny circle. _apply_state is the
        single chokepoint for geometry changes and calls this after each
        resize.

        shape:
          'circle' - idle coin: full ellipse (a circle for the square window)
          'pill'   - recording strip: stadium (corner radius = height / 2,
                     so the short ends are perfect semicircles)
        """
        try:
            self.root.update_idletasks()   # flush the pending geometry change
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            if w <= 1 or h <= 1:
                return

            user32 = ctypes.windll.user32
            gdi = ctypes.windll.gdi32
            # 64-bit safety: without explicit types, ctypes marshals HWND/HRGN
            # as 32-bit int and truncates the handle, so SetWindowRgn would
            # target the wrong window or get a junk region. Declare pointer-
            # width types. Idempotent - safe to set on every call.
            user32.GetParent.restype = ctypes.c_void_p
            user32.GetParent.argtypes = [ctypes.c_void_p]
            gdi.CreateEllipticRgn.restype = ctypes.c_void_p
            gdi.CreateRoundRectRgn.restype = ctypes.c_void_p
            user32.SetWindowRgn.restype = ctypes.c_int
            user32.SetWindowRgn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]

            win_id = self.root.winfo_id()
            hwnd = user32.GetParent(win_id) or win_id

            # Region right/bottom edges are EXCLUSIVE, so +1 to include the
            # final row/column of pixels.
            if shape == "circle":
                rgn = gdi.CreateEllipticRgn(0, 0, w + 1, h + 1)
            else:  # 'pill' / stadium
                # Ellipse axes = height -> corner radius = height/2, which
                # rounds the short ends into full semicircles.
                rgn = gdi.CreateRoundRectRgn(0, 0, w + 1, h + 1, h, h)
            # SetWindowRgn takes OWNERSHIP of the GDI region object; the OS
            # frees it. Do NOT DeleteObject(rgn) afterwards.
            user32.SetWindowRgn(hwnd, rgn, True)
        except Exception:
            pass  # Non-Windows or API failure: window stays rectangular

    # ── Monitor-aware corner anchoring ──────────────────────────────────────

    _MARGIN_X = 24   # px from the left/right edge of the work-area
    # v2.5.6: was 60, which floated the dot high above the taskbar. 12px sits
    # it JUST above the taskbar (the work-area bottom already excludes the
    # taskbar, so this is a 12px breathing gap, not 12px from the screen edge).
    _MARGIN_Y = 12   # px above the work-area bottom (just above the taskbar)

    def _placement_anchor_x(self, mx: int, mw: int) -> int:
        """Compute the anchor x for the current WIDGET_PLACEMENT within a
        monitor work-area starting at mx with width mw.

        The anchor's MEANING depends on placement (see _widget_left):
          bottom_right  -> anchor = right edge
          bottom_center -> anchor = horizontal center
          bottom_left   -> anchor = left edge
        """
        if WIDGET_PLACEMENT == "bottom_center":
            return mx + mw // 2
        if WIDGET_PLACEMENT == "bottom_left":
            return mx + self._MARGIN_X
        return mx + mw - self._MARGIN_X   # bottom_right (default)

    def _widget_left(self, w: int) -> int:
        """Window left-x for a widget of width w, honoring the placement.

        The widget grows from its anchor differently per placement so the
        idle->record expansion reads naturally:
          bottom_right  -> grows leftward  (anchor = right edge)
          bottom_center -> grows symmetric (anchor = center)
          bottom_left   -> grows rightward (anchor = left edge)

        Manual drag (_user_placed) always uses bottom-right semantics because
        _drag_move stores the dropped bottom-right corner as the anchor.
        """
        if self._user_placed or WIDGET_PLACEMENT == "bottom_right":
            return self._anchor_x - w
        if WIDGET_PLACEMENT == "bottom_center":
            return self._anchor_x - w // 2
        if WIDGET_PLACEMENT == "bottom_left":
            return self._anchor_x
        return self._anchor_x - w

    def _reanchor_current_monitor(self):
        """Recompute the anchor for the placement on the monitor the cursor
        is currently on, and move the window there now. Used when the user
        picks a new placement so the change is immediate."""
        info = _get_cursor_monitor_info()
        if info is not None:
            hmon, (mx, my, mw, mh) = info
            self._anchored_hmon = hmon
        else:
            mx, my = 0, 0
            mw = self.root.winfo_screenwidth()
            mh = self.root.winfo_screenheight()
        self._anchor_x = self._placement_anchor_x(mx, mw)
        self._anchor_y = my + mh - self._MARGIN_Y
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        self.root.geometry(f"{w}x{h}+{self._widget_left(w)}+{self._anchor_y - h}")

    def _anchor_to_monitor(self):
        """Re-anchor the dot to the bottom-right of whichever monitor the
        cursor is currently on. Called from the heartbeat.

        v2.5.4 fix: cross-monitor cursor movement now overrides the
        _user_placed flag. The old logic kept _user_placed sticky forever
        once set, which silently broke "follow me to another screen" for
        anyone who had a saved position or had ever dragged the widget.

        Semantics now:
          - Same monitor as before  -> do nothing (respects intra-monitor
            drag placement, prevents post-wake jitter)
          - DIFFERENT physical monitor than current anchor -> follow,
            clearing _user_placed because the user has explicitly moved
            attention to a new screen
          - widget_follow_cursor=False in config -> never follow

        Identity comparison is by HMONITOR handle, not coordinates, so
        transient workarea changes (taskbar autohide, DPI re-init during
        sleep/wake) on the SAME monitor don't trigger movement.
        """
        if not _WIDGET_FOLLOW_CURSOR:
            return
        info = _get_cursor_monitor_info()
        if info is None:
            return  # can't tell - keep current position
        hmon, (mx, my, mw, mh) = info
        # Same monitor as current anchor -> respect user placement on this
        # screen, do nothing.
        if hmon == getattr(self, "_anchored_hmon", None):
            return
        # Different monitor. Even if the user previously dragged to a custom
        # position on the OLD monitor, follow them to the new monitor's
        # bottom-right. They've explicitly moved attention; we don't strand
        # the widget behind. Clear _user_placed so subsequent same-monitor
        # heartbeats don't try to snap back.
        log.debug(f"[Widget] cursor on new monitor (hmon={hmon}); following")
        self._anchored_hmon = hmon
        self._user_placed = False
        self._anchor_x = self._placement_anchor_x(mx, mw)
        self._anchor_y = my + mh - self._MARGIN_Y
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        self.root.geometry(f"{w}x{h}+{self._widget_left(w)}+{self._anchor_y - h}")

    def _is_offscreen(self) -> bool:
        """Return True if the widget is positioned outside all visible monitors."""
        try:
            # Use ROOTX/ROOTY (absolute screen coords) - winfo_x on an
            # overrideredirect Toplevel can return parent-relative coords
            # which are useless for off-screen detection.
            x = self.root.winfo_rootx()
            y = self.root.winfo_rooty()
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            # Use VIRTUAL SCREEN bounds (all monitors combined), not
            # winfo_screenwidth/height which return primary only. A widget
            # on a secondary monitor to the right would have x > primary_w,
            # which the old check incorrectly treated as "off screen" and
            # repeatedly reset to primary. Real fix: check against the
            # bounding box of ALL physical monitors.
            gm = ctypes.windll.user32.GetSystemMetrics
            vx, vy = gm(76), gm(77)            # SM_X/YVIRTUALSCREEN
            vw, vh = gm(78), gm(79)            # SM_CX/CYVIRTUALSCREEN
            # Widget is offscreen if it has no overlap with the virtual screen.
            # Use a 50 px slop in case window decorations push us just past edges.
            right, bottom = x + w, y + h
            if (right < vx - 50 or x > vx + vw + 50 or
                    bottom < vy - 50 or y > vy + vh + 50):
                return True
        except Exception:
            pass
        return False

    def reset_position(self):
        """Move the widget back to its placement position on the cursor's
        monitor (just above the taskbar). Called from the tray icon or when
        the widget is detected offscreen. Clears the user-placed flag so the
        heartbeat resumes cursor-following and removes the saved position."""
        try:
            self._user_placed = False
            try:
                # Remove the saved position so next launch uses cursor monitor
                with open(CONFIG_PATH) as f:
                    data = json.load(f)
                if "widget_position" in data:
                    data.pop("widget_position", None)
                    with open(CONFIG_PATH, "w") as f:
                        json.dump(data, f, indent=4)
                    log.info("Config: widget_position removed (reset_position)")
            except Exception:
                pass
            # Re-anchor using the work area (excludes taskbar) + placement, so
            # the dot lands just above the taskbar rather than behind it.
            self._reanchor_current_monitor()
            self.root.deiconify()
            self._force_topmost()
            log.info(f"Widget position reset ({WIDGET_PLACEMENT}, above taskbar)")
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
        """Permanent heartbeat: keeps the widget always-on-top, optionally
        re-anchors to cursor monitor (off by default since v2.5.1), and
        recovers the dot if it genuinely drifts off all screens.

        Wrapped in try/except so the heartbeat chain NEVER breaks - if it
        stops rescheduling, the widget becomes unreachable (no taskbar button).
        """
        try:
            self._force_topmost()
            self._anchor_to_monitor()
            # Auto-recover if the widget drifted offscreen.
            # v2.5.1: debounce. During sleep/wake transitions Windows may
            # briefly report widget coords that LOOK off-screen because DPI
            # is being re-applied or monitor enumeration is in flux. We now
            # require 3 consecutive offscreen reads before firing the rescue
            # reset - that gives transient post-wake states ~4.5s to settle.
            if self._is_offscreen():
                self._offscreen_strike_count = getattr(self, "_offscreen_strike_count", 0) + 1
                if self._offscreen_strike_count >= 3:
                    log.warning(
                        f"Widget detected offscreen for {self._offscreen_strike_count} "
                        f"consecutive heartbeats — resetting position"
                    )
                    self.reset_position()
                    self._offscreen_strike_count = 0
            else:
                # Reset the strike counter as soon as we see widget on-screen
                self._offscreen_strike_count = 0
        except Exception as e:
            log.error(f"Heartbeat error (recovering): {e}")
        # ALWAYS reschedule — this line must never be skipped
        # Heartbeat runs at 1500ms (was 500ms in v2.4 and earlier). Three checks
        # per second was wasteful - topmost rarely needs re-asserting that often
        # and monitor anchoring happens once per cursor-monitor transition.
        # 1.5s is fast enough to feel snappy on multi-monitor switches.
        self.root.after(1500, self._start_topmost_heartbeat)

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
            self._dot.pack(fill="both", expand=True)
            # v2.5.1: full opacity in idle state. Transparency is handled by
            # the -transparentcolor key (magenta pixels invisible), so the
            # actual painted brand mark stays crisp. Old behavior used alpha
            # to fade the dot which made it muddy.
            self.root.attributes("-alpha", 1.0)
            self.root.geometry(
                f"{_W_DOT}x{_H_DOT}"
                f"+{self._widget_left(_W_DOT)}+{self._anchor_y - _H_DOT}"
            )
            # Clip the square window to a circle so the coin is a true round
            # mark (no square/squircle corners). Synchronous so the region
            # matches the size we just set.
            self._apply_window_region("circle")
            # Defer one tick so the Canvas has its dimensions before drawing
            self.root.after(0, self._refresh_idle_color)
        else:
            # Use the captured hands_free value (passed from set_state) so the
            # layout matches what was true at the moment of the call.
            hands_free_recording = (state == "recording" and hands_free_snap)

            # Pill width is LOCKED across a record -> process -> done flow so it
            # never resizes mid-session (the old code dropped from 240 to 168
            # when hands-free recording handed off to processing). We capture
            # the width when recording begins and reuse it for the follow-on
            # states. Loading / busy use the compact width.
            if state == "recording":
                self._session_width = _W_WAVE_HF if hands_free_snap else _W_WAVE
                w_outer = self._session_width
            elif state in ("processing", "done", "no_speech"):
                w_outer = getattr(self, "_session_width", _W_WAVE)
            else:  # loading, busy
                w_outer = _W_WAVE

            self._dot.pack_forget()
            border = _STATE_WAVE.get(state, ("", None, _BORDER_COLOR))[2]
            self._inner.pack(fill="both", expand=True, padx=_BORDER_PX, pady=_BORDER_PX)
            self.root.config(bg=border)
            self.root.attributes("-alpha", _ACTIVE_ALPHA)
            self.root.geometry(
                f"{w_outer}x{_H_WAVE}"
                f"+{self._widget_left(w_outer)}+{self._anchor_y - _H_WAVE}"
            )
            # Clip to a pill (stadium) shape. The right cap is a 16px-radius
            # semicircle = the resting coin, so the coin appears to stretch
            # into the strip. Synchronous so the region matches the new size.
            self._apply_window_region("pill")
            self._bar_h      = [0.08] * _N_BARS
            self._anim_phase = 0.0
            self._done_frame = 0   # fresh start for the done settle animation

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
            targets = self._compute_fft_bars()
            for i in range(_N_BARS):
                t = targets[i]
                # Asymmetric smoothing: fast attack, slow release. Bars snap
                # up to the sound instantly then ease back down - the "peak
                # meter" feel that reads alive/premium rather than mushy.
                if t > self._bar_h[i]:
                    self._bar_h[i] = self._bar_h[i] * 0.35 + t * 0.65
                else:
                    self._bar_h[i] = self._bar_h[i] * 0.80 + t * 0.20
            self._draw_bars(self._bar_h, wave, glow)

        elif state == "loading":
            # "Warming up" (startup): a calm symmetric BREATH - bars swell and
            # ebb together with a soft center bias and a gentle shimmer, like
            # the app inhaling as it wakes. On-brand coral, distinct from the
            # reactive recording bloom and the processing flow. Loops until the
            # model is ready, however long that takes.
            wave, glow, _ = _STATE_WAVE["loading"]
            self._anim_phase += 0.16                       # slow, calm
            breath = 0.5 + 0.5 * math.sin(self._anim_phase)   # global 0..1
            center = (_N_BARS - 1) / 2.0
            for i in range(_N_BARS):
                d = abs(i - center) / center               # symmetric
                shimmer = 0.5 + 0.5 * math.sin(self._anim_phase * 1.3 - d * 3.0)
                env = 1.0 - 0.30 * d                        # center a touch taller
                self._bar_h[i] = 0.08 + 0.28 * breath * env * (0.55 + 0.45 * shimmer)
            self._draw_bars(self._bar_h, wave, glow)

        elif state == "processing":
            # "Thinking" flow: a sum of three traveling waves at INCOMMENSURATE
            # frequencies, so the pattern is quasi-periodic and never visibly
            # repeats. This kills the monotony of a single looping ripple on
            # long transcriptions while staying calm and on-brand. Symmetric
            # about the center (uses distance-from-center) so it matches the
            # bass-center language of recording and suits the centered pill.
            wave, glow, _ = _STATE_WAVE["processing"]
            self._anim_phase += 0.30
            p = self._anim_phase
            center = (_N_BARS - 1) / 2.0
            for i in range(_N_BARS):
                d = abs(i - center) / center               # 0 center .. 1 edge
                # Ratios 1 : 0.61 : 1.7 are mutually irrational-ish, so the
                # summed wave does not settle into an obvious loop.
                w = (        math.sin(p          - d * 2.2)
                     + 0.6 * math.sin(p * 0.61   - d * 3.7)
                     + 0.4 * math.sin(p * 1.70   + d * 1.3))
                norm = (w / 2.0) * 0.5 + 0.5               # ~0..1
                norm = min(1.0, max(0.0, norm))
                self._bar_h[i] = 0.10 + 0.32 * norm
            self._draw_bars(self._bar_h, wave, glow)

        elif state == "done":
            # Confident "settle": bloom to full, then collapse inward toward
            # the center and fade out (outer bars fall first), resolving the
            # energy to the middle before the pill morphs back to the coin.
            # The done cue plays once, on the first frame.
            wave, glow, _ = _STATE_WAVE["done"]
            df = getattr(self, "_done_frame", 0)
            if df == 0:
                _play_cue("done")
            df += 1
            self._done_frame = df
            total = 9                       # ~9 frames * 80ms ≈ 720ms
            progress = min(1.0, df / total)
            center = (_N_BARS - 1) / 2.0
            bars = []
            for i in range(_N_BARS):
                d = abs(i - center) / center        # 0 center .. 1 edge
                # Outer bars (high d) decay sooner -> energy gathers to center.
                # Tuned so edges hit floor by ~halfway and the center fully
                # resolves to floor by the final frame, for a clean settle
                # before the pill morphs back to the coin.
                local = max(0.0, 1.0 - progress * (1.0 + 1.0 * d))
                bars.append(0.06 + 0.86 * local)
            self._draw_bars(bars, wave, glow)
            if df >= total:
                self._done_frame = 0
                self._apply_state("idle")
            else:
                self._anim_job = self.root.after(80, self._animate)
            return

        else:
            return

        self._anim_job = self.root.after(80, self._animate)

    def _compute_fft_bars(self):
        """Real FFT frequency-spectrum bar heights (0..1), one per _N_BARS.

        Research finding (Wispr Flow / superwhisper-class apps and audio-viz
        UX guides): the "alive" look comes from a true FREQUENCY SPECTRUM,
        where each bar is a frequency band and the bars dance to the actual
        spectral content of your voice - not a single amplitude scaled by a
        fixed envelope + random jitter (which reads uniform and fake).

        Design choices grounded in that research:
          - log-spaced bands across the voice range (~80 Hz to ~4 kHz),
            since pitch perception is logarithmic
          - sqrt magnitude compression (raw FFT magnitudes are very peaky)
          - adaptive normalization via a slowly-decaying running peak, so
            quiet and loud voices are both well-scaled
          - BASS-CENTER SYMMETRIC layout: the lowest band sits in the middle
            and higher bands mirror outward to both ends. Voice energy is
            low-mid heavy, so the strip "blooms" from the center - which is
            exactly the motion that suits the new bottom-center placement.

        Returns a small baseline floor on silence or any failure so the
        strip never looks dead."""
        floor = 0.06
        try:
            if not _audio_frames:
                return [floor] * _N_BARS
            # Most recent ~2048 samples (~128ms @16kHz): a stable spectrum
            # with no perceptible lag. Concatenate the last few callback
            # chunks in case the block size is small.
            recent = list(_audio_frames)[-6:]
            chunk = np.concatenate([f.flatten() for f in recent]).astype(np.float32)
            if chunk.size < 128:
                return [floor] * _N_BARS
            chunk = chunk[-2048:]

            # Silence gate. Without this, the adaptive normalization below
            # divides by an ever-shrinking running peak during quiet moments,
            # so background noise gets amplified to full scale and the strip
            # "blooms on its own" even when you are not speaking. If the raw
            # signal RMS is below a speech floor, decay the peak and return a
            # flat baseline so the strip rests calmly until you actually talk.
            rms = float(np.sqrt(np.mean(chunk ** 2)))
            _SILENCE_RMS = 0.008   # ~-42 dBFS; well below normal speech (~0.05+)
            if rms < _SILENCE_RMS:
                self._fft_peak = max(getattr(self, "_fft_peak", 1e-6) * 0.92, 1e-6)
                return [floor] * _N_BARS

            # Hann window curbs spectral leakage between adjacent bands.
            windowed = chunk * np.hanning(chunk.size).astype(np.float32)
            spectrum = np.abs(np.fft.rfft(windowed))
            freqs = np.fft.rfftfreq(chunk.size, 1.0 / SAMPLE_RATE)

            # Half as many bands as bars; we mirror them for the symmetric look.
            n_half = (_N_BARS + 1) // 2
            edges = np.logspace(np.log10(80.0), np.log10(4000.0), n_half + 1)
            half = np.empty(n_half, dtype=np.float32)
            for b in range(n_half):
                mask = (freqs >= edges[b]) & (freqs < edges[b + 1])
                half[b] = spectrum[mask].mean() if np.any(mask) else 0.0

            half = np.sqrt(half)   # perceptual compression

            # Adaptive normalization: track a decaying running peak so the
            # bars auto-scale to the current speaking volume.
            cur_peak = float(half.max())
            prev_peak = getattr(self, "_fft_peak", 1e-6)
            peak = max(cur_peak, prev_peak * 0.92, 1e-6)
            self._fft_peak = peak
            norm = np.clip(half / peak, 0.0, 1.0)
            norm = floor + (1.0 - floor) * norm   # lift off the floor

            # Mirror into a bass-center symmetric array. Center bar = lowest
            # band; higher bands fan outward to both edges.
            bars = [floor] * _N_BARS
            center = _N_BARS // 2
            for k in range(n_half):
                v = float(norm[k])
                if center - k >= 0:
                    bars[center - k] = v
                if center + k < _N_BARS:
                    bars[center + k] = v
            return bars
        except Exception:
            return [floor] * _N_BARS

    # ── Waveform renderers ───────────────────────────────────────────────
    # Each style draws the same `heights` data (15 floats 0..1 representing
    # the audio envelope) in a different visual idiom. Switching styles is
    # a config setting (WAVEFORM_STYLE) exposed through the right-click
    # menu. _draw_bars is the legacy entry-point that dispatches to whichever
    # renderer is active so callers in _animate don't need to know the choice.

    def _draw_bars(self, heights, color, glow=None):
        """Dispatch the configured waveform style for the current frame."""
        dispatch = {
            "wave_filled":       self._draw_wave_filled,
            "bars_classic":      self._draw_bars_classic,
            "bars_mirror":       self._draw_bars_mirror,
            "dots":              self._draw_dots,
            "line_oscilloscope": self._draw_line_oscilloscope,
            "blocks_brutalist":  self._draw_blocks_brutalist,
        }
        fn = dispatch.get(WAVEFORM_STYLE, self._draw_bars_mirror)
        # Clear-and-recreate every frame. Cheap for 15-element scenes at
        # ~12 fps and avoids any cross-style state when the user switches.
        self._canvas.delete("all")
        fn(heights, color, glow)

    def _wave_geom(self, heights):
        """Common geometry helper. Returns (canvas, cw, ch, cy, max_amp, n)."""
        c  = self._canvas
        cw = c.winfo_width()  or (_W_WAVE - 18)
        ch = c.winfo_height() or _H_WAVE
        return c, cw, ch, ch / 2, max(1.0, (ch - 6) / 2), len(heights)

    def _draw_wave_filled(self, heights, color, glow=None):
        """Smooth filled wave - the original v2.x look. Optional glow halo."""
        c, cw, ch, cy, max_amp, n = self._wave_geom(heights)

        def _poly(scale):
            top, bot = [], []
            for i, h in enumerate(heights):
                x   = 2 + (i / max(n - 1, 1)) * (cw - 4)
                amp = max(0.05, h) * max_amp * scale
                top.append((x, cy - amp))
                bot.append((x, cy + amp))
            return [v for pt in top for v in pt] + [v for pt in reversed(bot) for v in pt]

        if glow is not None:
            for scale, fill in ((1.5, glow), (1.15, glow)):
                pts = _poly(scale)
                if len(pts) >= 6:
                    c.create_polygon(*pts, smooth=True, splinesteps=32,
                                     fill=fill, outline="")
        pts = _poly(1.0)
        if len(pts) >= 6:
            c.create_polygon(*pts, smooth=True, splinesteps=32,
                             fill=color, outline="")

    def _draw_bars_classic(self, heights, color, glow=None):
        """Vertical pills from baseline. Classic equalizer."""
        c, cw, ch, cy, max_amp, n = self._wave_geom(heights)
        bar_w = 6
        total = n * bar_w
        gap   = max(2, (cw - total) // (n + 1))
        x = gap
        for h in heights:
            amp = max(0.05, h) * max_amp
            c.create_oval(x, cy - amp, x + bar_w, cy + amp,
                          fill=color, outline="")
            x += bar_w + gap

    def _draw_bars_mirror(self, heights, color, glow=None):
        """Center-mirrored bars with a small gap. Premium audio-meter look."""
        c, cw, ch, cy, max_amp, n = self._wave_geom(heights)
        bar_w = 5
        total = n * bar_w
        gap   = max(2, (cw - total) // (n + 1))
        center_gap = 2
        x = gap
        r = bar_w / 2
        for h in heights:
            amp = max(0.05, h) * max_amp
            # Top pill
            c.create_rectangle(x, cy - amp, x + bar_w, cy - center_gap,
                               fill=color, outline="")
            c.create_oval(x, cy - amp - r, x + bar_w, cy - amp + r,
                          fill=color, outline="")
            # Bottom pill
            c.create_rectangle(x, cy + center_gap, x + bar_w, cy + amp,
                               fill=color, outline="")
            c.create_oval(x, cy + amp - r, x + bar_w, cy + amp + r,
                          fill=color, outline="")
            x += bar_w + gap

    def _draw_dots(self, heights, color, glow=None):
        """Pulsing dots whose radius tracks amplitude."""
        c, cw, ch, cy, max_amp, n = self._wave_geom(heights)
        spacing = (cw - 12) / max(n - 1, 1)
        for i, h in enumerate(heights):
            x = 6 + i * spacing
            r = 1.2 + max(0.05, h) * 7.5
            c.create_oval(x - r, cy - r, x + r, cy + r,
                          fill=color, outline="")

    def _draw_line_oscilloscope(self, heights, color, glow=None):
        """Thin oscilloscope-style zigzag line through the data points."""
        c, cw, ch, cy, max_amp, n = self._wave_geom(heights)
        pts = []
        for i, h in enumerate(heights):
            x = 4 + (i / max(n - 1, 1)) * (cw - 8)
            sign = 1 if i % 2 == 0 else -1
            y = cy + sign * max(0.05, h) * max_amp * 0.85
            pts.append((x, y))
        # Stroke
        flat = [v for p in pts for v in p]
        if len(flat) >= 4:
            c.create_line(*flat, fill=color, width=2, capstyle="round",
                          joinstyle="round")
        # Peak dots
        for x, y in pts:
            c.create_oval(x - 1.5, y - 1.5, x + 1.5, y + 1.5,
                          fill=color, outline="")

    def _draw_blocks_brutalist(self, heights, color, glow=None):
        """Segmented LED-style stacked rectangles. Editorial / brutalist."""
        c, cw, ch, cy, max_amp, n = self._wave_geom(heights)
        bar_w = 7
        total = n * bar_w
        gap   = max(2, (cw - total) // (n + 1))
        seg_h = 3
        seg_gap = 1
        x = gap
        for h in heights:
            amp = max(0.05, h) * max_amp
            n_segs = max(1, int(amp / (seg_h + seg_gap)))
            for s in range(n_segs):
                y1 = cy - (s + 1) * (seg_h + seg_gap) + seg_gap
                y2 = y1 + seg_h
                c.create_rectangle(x, y1, x + bar_w, y2,
                                   fill=color, outline="")
                # Mirror below the center line
                c.create_rectangle(x, ch - y2, x + bar_w, ch - y1,
                                   fill=color, outline="")
            x += bar_w + gap

    def _styled_menu(self, parent) -> tk.Menu:
        """Construct a brand-styled tk.Menu (Tk lets us override the OS
        defaults). Used for the main right-click menu and every cascade.

        Brand palette applied:
          - bg               INK         (dark surface)
          - fg               PAPER       (warm light text)
          - activebackground CORAL       (highlight on hover)
          - activeforeground INK         (dark text on coral)
          - bd=0             flat        (no Windows raised border)
        """
        return tk.Menu(
            parent, tearoff=0,
            bg=theme.INK, fg=theme.PAPER,
            activebackground=theme.CORAL,
            activeforeground=theme.INK,
            activeborderwidth=0, bd=0,
            font=(theme.FONT_FAMILY, 9),
            relief="flat",
        )

    def _rebuild_menu(self):
        """Rebuild the right-click context menu.
        Called once at startup and again after a model switch so checkmarks update."""
        m = self._menu
        m.delete(0, "end")

        # Brand header: Tk system menus can't compose multiple text styles,
        # so the lockup appears as plain text. The Settings tab in the
        # history window carries the styled "Cait. whisper" lockup.
        m.add_command(label="Cait. whisper", state="disabled",
                      font=(theme.FONT_FAMILY_TIGHT, 10, "bold"))
        m.add_separator()

        # ── Switch Model cascade ──────────────────────────────────────────────
        switch_menu = self._styled_menu(m)

        moon_menu = self._styled_menu(switch_menu)
        for mdl in _MOONSHINE_MODELS:
            active = (_current_engine == "moonshine" and _current_model == mdl)
            lbl    = f"✓  {mdl}" if active else f"    {mdl}"
            moon_menu.add_command(
                label=lbl,
                command=lambda e="moonshine", mo=mdl: _switch_model(e, mo),
            )

        whis_menu = self._styled_menu(switch_menu)
        for mdl in _WHISPER_MODELS:
            active = (_current_engine == "whisper" and _current_model == mdl)
            lbl    = f"✓  {mdl}" if active else f"    {mdl}"
            whis_menu.add_command(
                label=lbl,
                command=lambda e="whisper", mo=mdl: _switch_model(e, mo),
            )

        para_menu = self._styled_menu(switch_menu)
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

        # ── Re-transcribe last (try a different engine on the saved audio) ────
        # Disabled when no audio is cached. Lists every model so users can
        # easily flip from Moonshine to Whisper after a hallucination.
        retry_menu = self._styled_menu(m)
        with _last_frames_lock:
            has_cached = bool(_last_frames)
            cached_secs = sum(len(f) for f in _last_frames) / SAMPLE_RATE if _last_frames else 0
        if has_cached:
            # Quick "same engine" option at the top (also Shift+Alt+T)
            retry_menu.add_command(
                label=f"Same engine  (Shift+Alt+T)  ·  {cached_secs:.1f}s cached",
                command=lambda: threading.Thread(
                    target=lambda: _retranscribe_last("", ""),
                    daemon=True, name="retranscribe-menu",
                ).start(),
            )
            retry_menu.add_separator()
            for mdl in _MOONSHINE_MODELS:
                retry_menu.add_command(
                    label=f"Moonshine · {mdl}",
                    command=lambda mo=mdl: threading.Thread(
                        target=lambda m=mo: _retranscribe_last("moonshine", m),
                        daemon=True, name="retranscribe-menu",
                    ).start(),
                )
            for mdl in _WHISPER_MODELS:
                retry_menu.add_command(
                    label=f"Whisper · {mdl}",
                    command=lambda mo=mdl: threading.Thread(
                        target=lambda m=mo: _retranscribe_last("whisper", m),
                        daemon=True, name="retranscribe-menu",
                    ).start(),
                )
            if _nemo_available:
                for mdl in _PARAKEET_MODELS:
                    retry_menu.add_command(
                        label=f"Parakeet · {mdl}",
                        command=lambda mo=mdl: threading.Thread(
                            target=lambda m=mo: _retranscribe_last("parakeet", m),
                            daemon=True, name="retranscribe-menu",
                        ).start(),
                    )
        else:
            retry_menu.add_command(label="    (no recording cached yet)", state="disabled")
        m.add_cascade(label="Re-transcribe last  ▸", menu=retry_menu)

        # ── Microphone picker ─────────────────────────────────────────────────
        # Lets the user switch input devices without restarting the app or
        # changing the Windows default. Use case: laptop mic in quiet rooms,
        # Jabra/AirPods with noise cancellation in cafes, etc.
        mic_menu = self._styled_menu(m)
        try:
            devices = _list_input_devices()
        except Exception as e:
            log.warning(f"[Menu] could not list input devices: {e}")
            devices = []
        # Always offer "System default" as the top option
        default_active = (not INPUT_DEVICE)
        mic_menu.add_command(
            label=("✓  System default" if default_active else "    System default"),
            command=lambda: threading.Thread(
                target=_switch_input_device, args=("",),
                daemon=True, name="mic-switch",
            ).start(),
        )
        mic_menu.add_separator()
        for dev in devices:
            # "Active" = the configured name is a substring of this device name
            active = bool(INPUT_DEVICE) and INPUT_DEVICE.lower() in dev["name"].lower()
            prefix = "✓  " if active else "    "
            # Truncate for display; include a hint when the device is the
            # Windows default so users can orient themselves.
            display = dev["name"]
            if len(display) > 42:
                display = display[:39] + "..."
            if dev.get("is_default"):
                display += "  (default)"
            mic_menu.add_command(
                label=prefix + display,
                # Capture the name as a short substring that will still
                # resolve correctly next launch, even if hostapi changes.
                command=lambda n=dev["name"][:30]: threading.Thread(
                    target=_switch_input_device, args=(n,),
                    daemon=True, name="mic-switch",
                ).start(),
            )
        if not devices:
            mic_menu.add_command(label="    (no input devices found)", state="disabled")
        m.add_cascade(label="Microphone  ▸", menu=mic_menu)
        m.add_separator()

        # ── Audio cues submenu ────────────────────────────────────────────────
        cue_menu = self._styled_menu(m)
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

        # ── Waveform style submenu ────────────────────────────────────────────
        # User-pickable visual rhythm for the active recording strip. Each
        # entry maps to a _draw_* method on StatusWidget; see WAVEFORM_STYLES.
        wave_menu = self._styled_menu(m)
        for style_id, style_label in WAVEFORM_STYLES:
            active = (WAVEFORM_STYLE == style_id)
            lbl    = f"✓  {style_label}" if active else f"    {style_label}"
            wave_menu.add_command(
                label=lbl,
                command=lambda s=style_id: _set_waveform_style(s),
            )
        m.add_cascade(label="Waveform  ▸", menu=wave_menu)

        # ── Placement submenu ─────────────────────────────────────────────────
        # Where the dot rests on the active monitor. Composes with cursor-
        # follow (anchors at this spot on whichever monitor you're on).
        place_menu = self._styled_menu(m)
        for place_id, place_label in WIDGET_PLACEMENTS:
            active = (WIDGET_PLACEMENT == place_id)
            lbl    = f"✓  {place_label}" if active else f"    {place_label}"
            place_menu.add_command(
                label=lbl,
                command=lambda p=place_id: _set_widget_placement(p),
            )
        m.add_cascade(label="Placement  ▸", menu=place_menu)
        m.add_separator()

        # ── History & Dictionary ──────────────────────────────────────────────
        m.add_command(label="History & Dictionary", command=_open_history_window)
        m.add_command(label="View Log File", command=_open_log_file)
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

        # ── Sticky COMMAND mode toggle ───────────────────────────────────────
        # The primary way to fire a command is Shift+Alt+C (one-shot).
        # This toggle sets sticky mode for power users who want every utterance
        # to be classified without pressing Shift+Alt+C each time.
        m.add_command(
            label="Sticky COMMAND mode: ON" if _command_mode else "Sticky COMMAND mode: OFF",
            command=_toggle_command_mode,
        )

        # ── Two-pass transcription toggle ─────────────────────────────────────
        m.add_command(
            label="Two-Pass: ON" if _two_pass_enabled else "Two-Pass: OFF",
            command=_toggle_two_pass,
        )

        # ── Retroactive buffer toggle (v2.5.1) ────────────────────────────────
        # OFF by default - the always-on audio capture is wasteful for users
        # who never use Shift+Alt+R. Flip ON to enable the 20-second rolling
        # buffer (~1.3 MB resident plus the audio callback's lock+memcpy).
        m.add_command(
            label="Retro Buffer: ON" if _retro_enabled else "Retro Buffer: OFF",
            command=_toggle_retro_buffer,
        )

        # ── Screen-context OCR toggle (v2.3) ──────────────────────────────────
        m.add_command(
            label="Screen Context: ON" if _use_screen_context else "Screen Context: OFF",
            command=_toggle_screen_context,
        )

        # ── Dev logs toggle (v2.4) ────────────────────────────────────────────
        m.add_command(
            label="Dev Logs: ON" if _dev_logs else "Dev Logs: OFF",
            command=_toggle_dev_logs,
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
        # If the hover card is up, get rid of it immediately so the menu
        # has the screen to itself. Also cancel any pending show job that
        # would pop a card on top of the menu mid-click.
        if self._hover_show_job is not None:
            try: self.root.after_cancel(self._hover_show_job)
            except Exception: pass
            self._hover_show_job = None
        self._hide_hover_card()
        # Always rebuild so checkmarks and LLM label are current
        self._rebuild_menu()
        self._menu.tk_popup(event.x_root, event.y_root)
        # Stop the event propagating to parent widgets — without this, both
        # self._dot AND self.root fire _show_menu for the same click, the menu
        # opens twice in rapid succession and the first item-click gets eaten.
        return "break"

    # ── Hover status card ─────────────────────────────────────────────────
    # The card is a read-only status panel. There is nothing to click inside
    # it, so we hide it instantly when the cursor leaves the widget. We also
    # suppress it entirely while the right-click menu is open so the two UI
    # elements never fight for screen space.
    def _on_widget_hover(self, event):
        # Cancel any pending show/hide jobs — fresh intent wins
        if self._hover_hide_job is not None:
            try: self.root.after_cancel(self._hover_hide_job)
            except Exception: pass
            self._hover_hide_job = None
        # Do NOT show the card if the right-click menu is currently open
        try:
            if self._menu.winfo_ismapped():
                return
        except Exception:
            pass
        if self._hover_show_job is None and self._hover_card is None:
            self._hover_show_job = self.root.after(500, self._show_hover_card)

    def _on_widget_leave(self, event):
        # Cancel pending show
        if self._hover_show_job is not None:
            try: self.root.after_cancel(self._hover_show_job)
            except Exception: pass
            self._hover_show_job = None
        # Hide immediately; the card has no interactive elements so there's
        # nothing to preserve via a grace period.
        self._hide_hover_card()

    def _status_for_card(self):
        """Return (label, color) for the hover-card status pill, reflecting
        what Cait is doing right now. Priority order: live activity first,
        then actionable idle sub-states, then resting/ready.

        The Ready vs Resting split is meaningful: Ready = model loaded, next
        dictation is instant; Resting = model was unloaded after idle to free
        RAM, so the next dictation has a brief wake before it starts."""
        state = self._state
        if state == "recording":
            return ("Listening", theme.CORAL)
        if state == "processing":
            return ("Transcribing", theme.CORAL_SOFT)
        if state == "loading":
            return ("Warming up", theme.INFO)

        # Idle sub-states, most actionable first.
        if _correction_active:
            return ("Waiting to learn", theme.MUSTARD)
        if _one_shot_command:
            return ("Command armed", theme.CORAL)
        if _command_mode:
            return ("Command mode", theme.CORAL)
        if _asr_model is None:
            # Distinguish "never loaded yet" from "unloaded after idle".
            if _last_asr_use_time > 0:
                return ("Resting", theme.INK_FAINT)   # wakes on next dictation
            return ("Warming up", theme.INFO)          # first load in progress
        return ("Ready", theme.CORAL_SOFT)

    def _show_hover_card(self):
        """Build and display the hover card with current state."""
        self._hover_show_job = None
        if self._hover_card is not None:
            return
        # Double-check menu isn't open (could have opened during the delay)
        try:
            if self._menu.winfo_ismapped():
                return
        except Exception:
            pass

        card = tk.Toplevel(self.root)
        card.overrideredirect(True)
        card.attributes("-topmost", True)
        try:
            card.attributes("-alpha", 0.96)
        except Exception:
            pass
        # Don't let the card steal focus or keyboard events
        try:
            card.attributes("-disabled", True)
        except Exception:
            pass

        # Brand-token surface. INK_SOFT (elevated) with INK_MUTE 1-px border.
        frame = tk.Frame(card, bg=theme.INK_SOFT,
                         padx=theme.PAD_LG, pady=theme.PAD_MD,
                         highlightbackground=theme.INK_MUTE,
                         highlightthickness=theme.BORDER_THIN)
        frame.pack()

        # Title strip: brand mark + "Cait. whisper" lockup on the left, a
        # live status pill on the right. fill="x" so the status right-aligns.
        title_row = tk.Frame(frame, bg=theme.INK_SOFT)
        title_row.pack(anchor="w", fill="x", pady=(0, theme.PAD_SM))
        try:
            mark_photo = theme.get_mark_photo(
                18, border_color=theme.CORAL,
                glyph_color=theme.CORAL, fill_color=theme.INK_SOFT,
            )
            mark_lbl = tk.Label(title_row, image=mark_photo, bg=theme.INK_SOFT,
                                borderwidth=0, highlightthickness=0)
            mark_lbl._photo = mark_photo   # keep alive
            mark_lbl.pack(side="left", padx=(0, 6))
        except Exception:
            pass
        theme.brand_lockup(title_row, bg=theme.INK_SOFT, fg=theme.PAPER,
                           cait_size=12, period_size=14,
                           whisper_size=12).pack(side="left")

        # Status pill (top-right): a small coloured dot + a friendly word for
        # what Cait is doing right now. Tells the user at a glance whether the
        # next dictation is instant (Ready) or has a brief wake (Resting), and
        # surfaces the actionable states (Waiting to learn, Command mode).
        status_text, status_color = self._status_for_card()
        status_wrap = tk.Frame(title_row, bg=theme.INK_SOFT)
        status_wrap.pack(side="right", padx=(theme.PAD_LG, 0))
        dot = tk.Canvas(status_wrap, width=8, height=8, bg=theme.INK_SOFT,
                        highlightthickness=0, borderwidth=0)
        dot.create_oval(1, 1, 7, 7, fill=status_color, outline="")
        dot.pack(side="left", padx=(0, 5), pady=(0, 1))
        tk.Label(status_wrap, text=status_text, bg=theme.INK_SOFT,
                 fg=status_color, font=theme.t_caption()).pack(side="left")

        # ── Engine (full-width row; its value is long) ────────────────────
        eng_row = tk.Frame(frame, bg=theme.INK_SOFT)
        eng_row.pack(anchor="w", fill="x", pady=(0, theme.PAD_SM))
        tk.Label(eng_row, text="Engine", bg=theme.INK_SOFT, fg=theme.INK_FAINT,
                 font=theme.t_caption(), width=11, anchor="w").pack(side="left")
        tk.Label(eng_row, text=f"{_current_engine} · {_current_model}",
                 bg=theme.INK_SOFT, fg=theme.PAPER_WARM,
                 font=theme.t_small()).pack(side="left")

        # ── Settings grid: 2 columns so the 7 toggles take ~4 rows, not 7.
        # Each chip is a quiet dim label + a value coloured by state (active
        # = coral, off = faint), so you read the whole config at a glance
        # without the card growing tall.
        mode_label = "COMMAND" if _command_mode else "PURE"
        if _one_shot_command:
            mode_label = "COMMAND·1shot"
        chips = [
            ("Mode",         mode_label, (_command_mode or _one_shot_command)),
            ("Auto-Learn",   "ON" if _auto_learn_enabled else "OFF", _auto_learn_enabled),
            ("Two-Pass",     "ON" if _two_pass_enabled else "OFF", _two_pass_enabled),
            ("Screen Ctx",   "ON" if _use_screen_context else "OFF", _use_screen_context),
            ("LLM Cleanup",  "ON" if _post_process else "OFF", _post_process),
            ("Spoken Punct", "ON" if _spoken_punct else "OFF", _spoken_punct),
            ("Dev Logs",     "ON" if _dev_logs else "OFF", _dev_logs),
        ]
        grid = tk.Frame(frame, bg=theme.INK_SOFT)
        grid.pack(anchor="w", fill="x")
        for idx, (lab, val, on) in enumerate(chips):
            r, c = divmod(idx, 2)
            cell = tk.Frame(grid, bg=theme.INK_SOFT)
            cell.grid(row=r, column=c, sticky="w", padx=(0, theme.PAD_LG), pady=1)
            tk.Label(cell, text=lab, bg=theme.INK_SOFT, fg=theme.INK_FAINT,
                     font=theme.t_caption(), width=11, anchor="w").pack(side="left")
            tk.Label(cell, text=val, bg=theme.INK_SOFT,
                     fg=(theme.CORAL if on else theme.INK_FAINT),
                     font=theme.t_caption()).pack(side="left")

        # ── Watching status (only when correction-watch is armed) ─────────
        if _correction_active:
            w_row = tk.Frame(frame, bg=theme.INK_SOFT)
            w_row.pack(anchor="w", fill="x", pady=(theme.PAD_SM, 0))
            tk.Label(w_row, text="Watching", bg=theme.INK_SOFT, fg=theme.MUSTARD,
                     font=theme.t_caption(), width=11, anchor="w").pack(side="left")
            tk.Label(w_row, text="press Enter to teach", bg=theme.INK_SOFT,
                     fg=theme.MUSTARD, font=theme.t_caption()).pack(side="left")

        # ── Last paste (the most useful glance; full text, wrapped) ───────
        theme.divider_frame(frame).pack(fill="x", pady=(theme.PAD_MD, theme.PAD_SM))
        tk.Label(frame, text="LAST PASTE", bg=theme.INK_SOFT, fg=theme.CORAL,
                 font=theme.t_eyebrow(), anchor="w").pack(anchor="w")
        last = _last_transcription or ""
        if last:
            # Generous cap so very long dictations don't make an absurd card,
            # but we show far more than the old 37-char one-liner.
            shown = last if len(last) <= 320 else last[:317] + "..."
        else:
            shown = "Nothing dictated yet."
        tk.Label(frame, text=shown, bg=theme.INK_SOFT,
                 fg=(theme.PAPER if last else theme.INK_FAINT),
                 font=theme.t_small(), justify="left", anchor="w",
                 wraplength=300).pack(anchor="w", fill="x", pady=(2, 0))

        # Position: directly ABOVE the widget with a generous buffer so the
        # cursor travel path from any content above down to the dot is never
        # blocked by the card. Fall back to BELOW only if above would clip
        # the top of the monitor.
        #
        # Critical: use winfo_rootx/rooty, NOT winfo_x/winfo_y. On a Toplevel
        # created with overrideredirect(True) under Windows, winfo_x may
        # return parent-relative coordinates (often 0) rather than screen
        # coordinates. rootx/rooty are always absolute screen coordinates.
        #
        # v2.5.6 fix: clamp to the bounds of the monitor the WIDGET is on,
        # NOT the virtual screen (all monitors combined). The old virtual-
        # screen clamp let the card spill across the bezel onto a neighbour
        # monitor whenever the widget sat near a shared edge: the card was
        # centered on the widget, and since the virtual-screen right edge is
        # the FAR edge of the second monitor, no clamp fired and the card
        # bled / got truncated at the physical bezel. Confining to the
        # widget's own monitor keeps the whole card on one screen.
        card.update_idletasks()
        card_w = card.winfo_width()
        card_h = card.winfo_height()
        widget_x = self.root.winfo_rootx()
        widget_y = self.root.winfo_rooty()
        widget_w = self.root.winfo_width()
        widget_h = self.root.winfo_height()

        # Find the monitor that contains the widget's center point.
        center_x = widget_x + widget_w // 2
        center_y = widget_y + widget_h // 2
        bounds = _get_monitor_bounds_for_point(center_x, center_y, work_area=True)
        if bounds is None:
            # Fallback: virtual-screen bounds (old behavior) if the Win32
            # monitor query fails. Better a card that might bleed than no card.
            try:
                gm = ctypes.windll.user32.GetSystemMetrics
                bounds = (gm(76), gm(77), gm(78), gm(79))
            except Exception:
                bounds = (0, 0, self.root.winfo_screenwidth(),
                          self.root.winfo_screenheight())
        mon_x, mon_y, mon_w, mon_h = bounds

        # Horizontal: center the card on the widget, clamped to THIS monitor.
        # If the card is wider than the monitor (shouldn't happen) the max()
        # wins so the left edge stays on-screen.
        x = widget_x + (widget_w // 2) - (card_w // 2)
        x = max(mon_x + 8, min(x, mon_x + mon_w - card_w - 8))

        # Vertical: prefer ABOVE the widget with a 12 px gap. Fall back to
        # BELOW only if above would clip the top of this monitor.
        y = widget_y - card_h - 12
        if y < mon_y + 8:
            y = widget_y + widget_h + 12
        y = min(y, mon_y + mon_h - card_h - 8)

        card.geometry(f"+{x}+{y}")
        self._hover_card = card

    def _hide_hover_card(self):
        self._hover_hide_job = None
        if self._hover_card is not None:
            try:
                self._hover_card.destroy()
            except Exception:
                pass
            self._hover_card = None

    def _toggle_llm(self):
        global _post_process
        _post_process = not _post_process
        _save_config_key("post_process", _post_process)
        log.info(f"LLM cleanup {'enabled' if _post_process else 'disabled'}")
        # Rebuild the menu so the next right-click shows the new label.
        # Removed the brittle entryconfig(6, ...) magic-number that broke
        # whenever menu items were added/removed above this one.
        self.root.after(0, self._rebuild_menu)
        # Only manage the local Ollama subprocess if that's actually the
        # configured provider. With openai_compatible we'd uselessly spawn
        # a server that never gets called.
        try:
            from config_io import load_config
            provider = load_config().get("llm_provider", "local_ollama")
        except Exception:
            provider = "local_ollama"
        if _post_process and provider == "local_ollama":
            threading.Thread(target=_start_ollama_service, daemon=True, name="ollama-start").start()
        elif not _post_process:
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
        # Mark widget as user-placed so the heartbeat stops auto-anchoring
        # it to the cursor's monitor. Persist to config so it survives restart.
        self._user_placed = True
        try:
            _save_config_keys({"widget_position": {"x": self._anchor_x, "y": self._anchor_y}})
        except Exception:
            pass

    def _refresh_idle_color(self):
        """Re-apply idle dot appearance based on current state.

        The idle dot carries three orthogonal signals:
          1. Correction watch armed -> amber pulse (most pronounced, short-lived)
          2. Mode (PURE vs COMMAND) -> color + glyph
             - PURE:    filled circle ●, idle gray
             - COMMAND: hollow circle ◎, saturated blue
          3. Transient overlays (ready toast, etc.) are layered by other methods.

        The amber pulse is implemented via a recursive after() job that toggles
        between two amber shades so the user can see the app is "watching"
        even out of peripheral vision.
        """
        if self._state != "idle":
            return
        # Always cancel any running pulse before deciding; fresh state wins.
        self._stop_watch_pulse()

        if _correction_active:
            # Pulsing amber draws the eye; start the animation.
            self._start_watch_pulse()
            return

        # Paint the brand mark in the right colors per state.
        # All variants use a dark INK coin backdrop so the ring and Φ render
        # crisply against a solid surface (no anti-alias fringing against the
        # transparent magenta key). The square canvas corners stay transparent
        # so the visible result is a floating coin, not a square chip.
        #
        # Color hierarchy:
        #   PURE     - quiet INK_FAINT (muted gray) ring + Φ on dark coin.
        #              The resting state is intentionally low-attention;
        #              it should READ as "here, but not asking for anything".
        #              Coral is reserved for activity so any color shift
        #              draws the eye.
        #   ONE-SHOT - filled CORAL_SOFT coin, ink Φ (one command armed).
        #   COMMAND  - filled CORAL coin, ink Φ (sticky listening).
        #   READY    - brief CORAL_SOFT flash via _show_ready_toast on
        #              model-load, then snaps back to PURE.
        if _one_shot_command:
            self._redraw_mark(border=theme.CORAL_SOFT,
                              fill=theme.CORAL_SOFT,
                              glyph=theme.INK)
        elif _command_mode:
            self._redraw_mark(border=theme.CORAL,
                              fill=theme.CORAL,
                              glyph=theme.INK)
        else:
            # PURE idle: deeply muted INK_MUTE ring + Φ on a dark INK coin.
            # INK_MUTE (#5a5448) is the darkest readable gray in the brand
            # palette and the same color used for every other border in the
            # app, so the resting coin reads as a quiet container outline,
            # not as an active element. The mark only lights up (coral /
            # mustard / coral_soft) when there's an actual activity to
            # signal: startup ready, command mode, watch pulse.
            self._redraw_mark(border=theme.INK_MUTE,
                              fill=theme.INK,
                              glyph=theme.INK_MUTE)

    def _redraw_mark(self, *, border: str, glyph: str, fill: str = None):
        """Paint the brand mark on the dot canvas via PIL.

        v2.5.5: Canvas + window bg is ALWAYS INK (dark). We do NOT depend
        on -transparentcolor for the canvas corners. That Windows-specific
        key-color trick is unreliable across display drivers, color
        profiles, and wide-gamut monitors - on some setups the magenta
        leaks through as visible pink corners, which is exactly the
        regression that prompted this rewrite.

        Trade-off: the widget is now a small dark badge instead of a
        floating ring. On Win11 the DWM corner rounding turns it into a
        squircle. On dark wallpapers it's nearly invisible at rest. On
        light wallpapers it's a small dark element, which reads as a real
        UI affordance instead of a magic floating circle.

        The PIL image still carries its own alpha channel for the area
        outside the circle, so those pixels show the canvas bg (INK) and
        blend with the window bg cleanly.

        Args:
            border: ring stroke color
            glyph:  Φ text color
            fill:   inner disc color, or None for ring-only (then the INK
                    window bg shows inside the ring too)
        """
        self._dot.config(bg=theme.INK)
        self.root.config(bg=theme.INK)
        self._dot.delete("all")
        theme.draw_widget_mark(
            self._dot, _W_DOT,
            border_color=border, glyph_color=glyph, fill_color=fill,
        )

    # ── Amber pulse for correction watch ──────────────────────────────────
    def _start_watch_pulse(self):
        """Kick off the amber pulse animation. Idempotent; _stop cancels it."""
        self._pulse_phase = 0
        self._tick_watch_pulse()

    def _stop_watch_pulse(self):
        job = getattr(self, "_pulse_job", None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        self._pulse_job = None

    def _tick_watch_pulse(self):
        """Toggle between mustard shades every ~600ms for a soft pulse.
        Brand jewelry: mustard = 'watching' signal. Filled circle + Φ flip
        between brighter and dimmer to draw peripheral vision."""
        if self._state != "idle" or not _correction_active:
            self._stop_watch_pulse()
            return
        shade = theme.MUSTARD if (self._pulse_phase % 2 == 0) else theme.MUSTARD_SOFT
        self._redraw_mark(border=shade, fill=shade, glyph=theme.INK)
        self._pulse_phase += 1
        self._pulse_job = self.root.after(600, self._tick_watch_pulse)

    def _show_ready_toast(self):
        """Briefly flash the mark in coral-soft when ASR is loaded and ready.
        Uses CORAL_SOFT (brand jewelry) instead of a green/success color so
        we stay on palette."""
        if self._state != "idle":
            return
        self._redraw_mark(border=theme.CORAL_SOFT, fill=theme.CORAL_SOFT, glyph=theme.INK)
        def _revert():
            try:
                # Defer to the idle-color refresh which knows the right state.
                # Transparency is via -transparentcolor, no alpha needed.
                self._refresh_idle_color()
            except Exception:
                pass
        self.root.after(2000, _revert)

    def _notify_dict_learned(self, original: str, replacement: str):
        """Briefly flash a toast label on the widget when a dictionary entry is learned.
        Uses CORAL_SOFT on INK_SOFT (brand jewelry) instead of green/success
        to stay on palette."""
        try:
            toast = tk.Label(
                self._inner,
                text=f"'{original}' → '{replacement}'",
                bg=theme.INK_SOFT, fg=theme.CORAL_SOFT,
                font=theme.t_small(), padx=theme.PAD_MD, pady=theme.PAD_XS,
            )
            toast.place(relx=0.5, rely=0.5, anchor="center")
            self.root.after(2800, toast.destroy)
        except Exception:
            pass

    def _notify_dict_pending(self, original: str, replacement: str, count: int, threshold: int):
        """Flash a toast when a correction candidate is seen but not yet promoted.
        Shows the user exactly how many more corrections are needed, so the
        pending queue isn't invisible.

        MUSTARD = brand 'watching' jewelry, matches the watch-pulse on the
        widget mark for visual continuity."""
        try:
            remaining = threshold - count
            if remaining > 0:
                text = f"'{original}' → '{replacement}' ({count}/{threshold} · {remaining} more)"
            else:
                text = f"'{original}' → '{replacement}' ({count}/{threshold})"
            toast = tk.Label(
                self._inner,
                text=text,
                bg=theme.INK_SOFT, fg=theme.MUSTARD,
                font=theme.t_small(), padx=theme.PAD_MD, pady=theme.PAD_XS,
            )
            toast.place(relx=0.5, rely=0.5, anchor="center")
            self.root.after(3500, toast.destroy)
        except Exception:
            pass

    def _notify_retro_disabled(self):
        """Toast shown when Shift+Alt+R is pressed but the retro buffer is off."""
        try:
            toast = tk.Label(
                self._inner,
                text="Retro buffer is OFF\nEnable via right-click menu",
                bg=theme.INK_SOFT, fg=theme.MUSTARD,
                font=theme.t_small(), padx=theme.PAD_MD, pady=theme.PAD_XS,
                justify="center",
            )
            toast.place(relx=0.5, rely=0.5, anchor="center")
            self.root.after(3500, toast.destroy)
        except Exception:
            pass

    def _notify_bg_transcription(self, bg_text: str):
        """Toast that the background engine produced a better transcription.
        Stays visible a bit longer (4 seconds) because the user needs to
        decide whether to press Alt+Shift+Z to swap the pasted text.

        INFO blue is the one cool, non-brand accent reserved for two-pass
        availability cues, distinct from any state the widget mark uses."""
        try:
            preview = (bg_text[:40] + "…") if len(bg_text) > 40 else bg_text
            toast = tk.Label(
                self._inner,
                text=f"Better version available · Alt+Shift+Z\n{preview}",
                bg=theme.INK_SOFT, fg=theme.INFO,
                font=theme.t_small(), padx=theme.PAD_MD, pady=theme.PAD_XS,
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
    if cw_paths.is_frozen():
        # Frozen: no .py on disk to run. Re-launch our own exe with a flag
        # that the bundle entry (cait_whisper.py) routes to the history window.
        cmd = [sys.executable, "--history-window"]
    else:
        cmd = [sys.executable, str(cw_paths.app_dir() / "history_window.py")]
    _history_proc = subprocess.Popen(cmd, cwd=str(cw_paths.app_dir()))
    log.info("[HistoryWindow] launched as pid %d", _history_proc.pid)


def _open_log_file():
    """Open cait-whisper.log in the user's default text handler.
    Handy for debugging without having to find the file manually."""
    try:
        os.startfile(str(_LOG_PATH))  # Windows-only; opens with default handler
        log.info(f"[ViewLog] opened {_LOG_PATH}")
    except Exception as e:
        log.warning(f"[ViewLog] could not open log file: {e}")


# ─── Globals ──────────────────────────────────────────────────────────────────
_widget: StatusWidget = None
_tray   = None          # pystray.Icon — set in main()
_stream = None          # sd.InputStream — set in main()
_splash = None          # splash.SplashScreen — shown during startup model load

_recording    = False
_processing   = False   # True while _transcribe_and_paste is running
# Max ~5 min of audio at 16 kHz, blocksize 1024 → ~4688 chunks (~19 MB).
# deque silently drops oldest frames if a hands-free session runs very long.
_MAX_AUDIO_CHUNKS = int(5 * 60 * SAMPLE_RATE / 1024)
_audio_frames: collections.deque = collections.deque(maxlen=_MAX_AUDIO_CHUNKS)
_record_lock  = threading.Lock()

# ── Retroactive capture (v2.2) ──────────────────────────────────────────
# Always-on rolling buffer of the last ~20 seconds of audio. Independent of
# the main recording buffer above so hands-free recording is unaffected.
# Memory cost: 20 s * 16 kHz * 4 bytes (float32) ≈ 1.28 MB resident.
_RETRO_BUFFER_SECS    = 20
_RETRO_TRANSCRIBE_SECS = 15
_RETRO_MAX_CHUNKS     = int(_RETRO_BUFFER_SECS * SAMPLE_RATE / 1024)
_retro_frames: collections.deque = collections.deque(maxlen=_RETRO_MAX_CHUNKS)
_retro_lock   = threading.Lock()

# ── Last-recording cache (v2.5.0) ─────────────────────────────────────────
# After every recording we stash the raw frames so the user can retry with
# a different ASR engine when the first pass produced garbage (looped, low
# accuracy, etc). Just the most recent recording - one frames list at a time.
# Memory cost: ~32 KB/sec. A 60-second recording uses ~1.9 MB. Negligible.
_last_frames: list = []
_last_frames_lock = threading.Lock()

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

# ─── Input device helpers ────────────────────────────────────────────────
# Centralized so the device picker menu and stream-restart logic share
# the same resolution rules (case-insensitive substring match on device name).

def _list_input_devices() -> list[dict]:
    """Return a deduplicated list of input-capable devices on this system.
    Keys in each dict: name, index, hostapi, channels, samplerate, is_default.
    Deduplicates by name preferring WASAPI > DirectSound > MME for lowest
    latency on Windows."""
    try:
        all_devices = sd.query_devices()
        hostapis = sd.query_hostapis()
    except Exception as e:
        log.warning(f"[InputDevice] enumerate failed: {e}")
        return []

    # Hostapi preference score (lower = better latency on Windows).
    # WDM-KS is intentionally absent: PortAudio's WDM-KS support is fragile
    # (many WDM-KS-only devices return paInvalidDevice when opened), and
    # Microsoft documents WDM-KS as a debugging API not meant for app use.
    # Devices that ONLY expose WDM-KS get hidden from the menu - users can
    # still edit config.json manually if they need that path.
    hostapi_rank = {"Windows WASAPI": 0, "Windows DirectSound": 1, "MME": 2}
    HIDE_WDM_KS = True

    try:
        default_name = sd.query_devices(kind="input")["name"]
    except Exception:
        default_name = ""

    # Group by truncated display name (Windows sometimes truncates at 32 chars
    # across different hostapis, so match on the shorter name).
    # Skip obvious noise: kernel driver paths, pseudo-devices, speaker loopback.
    noise_markers = (
        "@system32",            # raw kernel driver path names
        "pc speaker",           # never useful as an input
        "primary sound capture",  # MME generic; real device also listed
        "microsoft sound mapper", # ditto
        "stereo mix",           # loopback; user almost never wants this
    )
    groups: dict[str, list[dict]] = {}
    for i, d in enumerate(all_devices):
        if d["max_input_channels"] <= 0:
            continue
        name = d["name"].strip()
        lower = name.lower()
        if any(m in lower for m in noise_markers):
            continue
        ha_name = hostapis[d["hostapi"]]["name"]
        # Drop WDM-KS-only entries unless we're keeping them
        if HIDE_WDM_KS and ha_name == "Windows WDM-KS":
            continue
        entry = {
            "index": i,
            "name": name,
            "hostapi": ha_name,
            "channels": d["max_input_channels"],
            "samplerate": int(d["default_samplerate"]),
            "rank": hostapi_rank.get(ha_name, 99),
        }
        # Key on first 28 chars to collapse truncation variants
        key = entry["name"][:28].lower()
        groups.setdefault(key, []).append(entry)

    # For each logical device, pick the best hostapi variant
    result = []
    for entries in groups.values():
        entries.sort(key=lambda e: e["rank"])
        best = entries[0]
        best["is_default"] = (best["name"][:28].lower() == default_name[:28].lower())
        result.append(best)

    # Sort: default first, then alphabetical
    result.sort(key=lambda e: (not e["is_default"], e["name"].lower()))
    return result


def _resolve_input_device(name_filter: str) -> int | None:
    """Find a device index matching `name_filter` (case-insensitive substring).
    Returns None if no match or empty filter. Callers should fall back to
    Windows default (device=None) when this returns None."""
    if not name_filter:
        return None
    needle = name_filter.strip().lower()
    if not needle:
        return None
    for dev in _list_input_devices():
        if needle in dev["name"].lower():
            log.info(f"[InputDevice] resolved {name_filter!r} -> [{dev['index']}] "
                     f"{dev['name']!r} ({dev['hostapi']})")
            return dev["index"]
    log.warning(f"[InputDevice] no match for {name_filter!r}; using system default")
    return None


def _switch_input_device(name: str):
    """Stop the current stream, open a new one bound to the selected device,
    and resume capture. Name is saved to config for next launch too.
    Empty string means system default."""
    global _stream, INPUT_DEVICE
    INPUT_DEVICE = name or ""
    _save_config_key("input_device", INPUT_DEVICE)

    device_idx = _resolve_input_device(INPUT_DEVICE) if INPUT_DEVICE else None
    log.info(f"[InputDevice] switching to {INPUT_DEVICE!r} (index={device_idx})")

    # Close current stream cleanly
    old = _stream
    _stream = None
    if old is not None:
        try:
            old.stop()
            old.close()
        except Exception as e:
            log.debug(f"[InputDevice] closing old stream failed (continuing): {e}")

    # Open new stream with the chosen device
    try:
        new_stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            callback=_audio_callback,
            blocksize=1024,
            device=device_idx,   # None = system default
        )
        new_stream.start()
        _stream = new_stream
        log.info(f"[InputDevice] switched successfully")
        # Rebuild the menu so the new active device shows a checkmark
        if _widget:
            _widget.root.after(0, _widget._rebuild_menu)
    except Exception as e:
        log.error(f"[InputDevice] could not open new stream: {e}")
        # Best-effort fallback: try default device
        try:
            fallback = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="float32",
                callback=_audio_callback,
                blocksize=1024,
            )
            fallback.start()
            _stream = fallback
            log.warning("[InputDevice] fell back to system default")
        except Exception as e2:
            log.error(f"[InputDevice] fallback also failed: {e2}")


def _audio_callback(indata, frames, time_info, status):
    if status:
        log.warning(f"Audio stream status: {status}")
    with _record_lock:
        if _recording:
            _audio_frames.append(indata.copy())
        # Retroactive capture: always buffer a rolling window, even when idle.
        # Tiny memory cost (~1.3 MB) in exchange for "grab the last 15 seconds".
        # Retroactive buffer fills ONLY when explicitly enabled by the user.
        # Default OFF saves a memcpy + lock acquire on every audio callback
        # (~64 KB/sec) and keeps the deque empty.
        if _retro_enabled:
            with _retro_lock:
                _retro_frames.append(indata.copy())

# ─── Transcribe + paste ───────────────────────────────────────────────────────

def _show_no_speech():
    """Show flat-bar waveform briefly to indicate no speech was detected."""
    if _widget:
        _widget.set_state("no_speech")


def _retranscribe_last(target_engine: str = "", target_model: str = ""):
    """Re-run the ASR pipeline on the most recently captured audio.

    Use cases:
      - Moonshine looped on a long word; user clicks "Re-transcribe last → Whisper"
      - User wants to compare engines on the same audio without re-speaking
      - First pass produced low-quality transcription; try again

    If target_engine and target_model are empty, retries with the currently
    active engine. Otherwise switches first, then transcribes.

    Refuses to fire while a recording or transcription is already in progress.
    """
    if _recording or _processing:
        log.info("[ReTranscribe] ignored (recording/processing busy)")
        return
    with _last_frames_lock:
        if not _last_frames:
            log.info("[ReTranscribe] no last recording cached")
            return
        frames_copy = list(_last_frames)
    secs = sum(len(f) for f in frames_copy) / SAMPLE_RATE
    log.info(f"[ReTranscribe] re-running ASR on last recording ({secs:.1f}s, {len(frames_copy)} chunks)")

    if _widget:
        _ui_after(0, lambda: _widget.set_state("processing"))

    def _do_retry():
        # Optional engine switch first. _switch_model is a no-op if same.
        if target_engine and target_model:
            log.info(f"[ReTranscribe] switching engine to {target_engine}/{target_model}")
            _switch_model(target_engine, target_model)
            # Wait briefly for the model to load. _switch_model spawns a thread;
            # poll _asr_lock until the new model is ready (max 30s).
            t0 = time.perf_counter()
            while time.perf_counter() - t0 < 30:
                with _asr_lock:
                    if (_current_engine == target_engine and
                        _current_model == target_model and
                        _asr_model is not None):
                        break
                time.sleep(0.1)
            else:
                log.warning("[ReTranscribe] model switch timed out; running with whatever loaded")
        # Re-run the full pipeline (spoken punct, dictionary, paste, etc.)
        _transcribe_and_paste(frames_copy)

    threading.Thread(target=_do_retry, daemon=True, name="re-transcribe").start()


def _trigger_retro_capture():
    """Retroactive capture (v2.2): transcribe the last ~15 seconds of audio
    from the rolling buffer. Bound to Shift+Alt+R. Refuses to fire while a
    recording or transcription is already in progress.

    v2.5.1: requires _retro_enabled to be ON. If OFF, briefly shows a
    helpful toast directing the user to the menu toggle."""
    if not _retro_enabled:
        log.info("[Retro] disabled - enable via right-click menu first")
        if _widget:
            _ui_after(0, _widget._notify_retro_disabled)
        return
    if _recording or _processing:
        log.info("[Retro] ignored (recording/processing busy)")
        return
    with _retro_lock:
        if not _retro_frames:
            log.info("[Retro] buffer is empty")
            return
        frames_snapshot = list(_retro_frames)
    # Trim to the most recent N seconds worth of chunks
    max_chunks = int(_RETRO_TRANSCRIBE_SECS * SAMPLE_RATE / 1024)
    if len(frames_snapshot) > max_chunks:
        frames_snapshot = frames_snapshot[-max_chunks:]
    secs = len(frames_snapshot) * 1024 / SAMPLE_RATE
    log.info(f"[Retro] transcribing last ~{secs:.1f}s ({len(frames_snapshot)} chunks)")
    if _widget:
        _ui_after(0, lambda: _widget.set_state("processing"))
    # Reuse the full transcription pipeline: ASR, spoken punct, LLM cleanup,
    # dictionary, paste, correction watch, two-pass. Same as a normal recording.
    threading.Thread(
        target=_transcribe_and_paste,
        args=(frames_snapshot,),
        daemon=True,
        name="retro-transcribe",
    ).start()


def _transcribe_and_paste(frames: list):
    global _processing, _last_transcription, _one_shot_command
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

        # Stash the raw frames for "Re-transcribe last" (Shift+Alt+T or menu).
        # Captured BEFORE any short/silent guards so even discarded recordings
        # can be retried with a different engine if the user wants to.
        # Skip captures that are clearly junk (< 0.5s) - retry won't help.
        if duration >= 0.5:
            global _last_frames
            with _last_frames_lock:
                _last_frames = list(frames)

        if duration < MIN_RECORD_SECS:
            log.info(f"Recording too short ({duration:.2f}s < {MIN_RECORD_SECS}s) — skipping ASR")
            _show_no_speech()
            return

        if rms < 0.0005:
            log.info("Audio is silent (RMS below threshold) — skipping ASR")
            _show_no_speech()
            return

        # ── Adaptive gain (v2.5.1) ───────────────────────────────────────────
        # Quiet recordings (distant mic, soft-spoken user, cafe headset at
        # low volume) make Whisper / Moonshine struggle. Normalize to a
        # target RMS so the model sees signal at the level it was trained on.
        # Caps gain at 8x to avoid pumping room noise; tanh-soft-clip
        # prevents distortion at the top.
        TARGET_RMS = 0.05    # roughly conversational speech level
        MAX_GAIN   = 8.0
        if 0.0005 <= rms < TARGET_RMS:
            gain = min(TARGET_RMS / rms, MAX_GAIN)
            audio_flat = audio_flat * gain
            # Soft-clip with tanh: linear for small values, smoothly compresses
            # peaks. Preserves dynamics better than hard clipping.
            audio_flat = (np.tanh(audio_flat * 0.7) / 0.7).astype(np.float32)
            new_rms = float(np.sqrt(np.mean(audio_flat ** 2)))
            log.info(f"AGC: gain={gain:.2f}x → new RMS={new_rms:.4f}")

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
        # ── Known-hallucination trailing-phrase strip (v2.5.1) ───────────────
        # Whisper is trained on a lot of YouTube content and has learned to
        # end transcriptions with stock phrases ("Thank you.", "Thanks for
        # watching.", "Please subscribe.") regardless of what was said.
        # When the audio ends and the model is uncertain, it tends to emit
        # one of these. If the LAST 1-5 words of the transcription match a
        # known stock phrase AND the rest is substantial, strip the tail.
        _TRAILING_HALLUCINATIONS = (
            # Each tuple is (lowercase phrase, must be at end). Match is case-
            # insensitive, punctuation-insensitive. Order matters - longer
            # phrases checked first so we don't strip just "thank" leaving "you".
            "thanks for watching",
            "please subscribe",
            "subscribe to my channel",
            "thank you for watching",
            "see you next time",
            "see you in the next video",
            "thanks for watching, and i'll see you in the next video",
            "thank you",
            "thanks",
        )
        if len(raw_words) >= 5:
            # Try each known phrase. Compare normalized trailing N words.
            # Only strip if there's substantial real content before the phrase.
            normalized_full = re.sub(r"[^\w\s]", "", raw_text).lower().strip()
            for phrase in _TRAILING_HALLUCINATIONS:
                phrase_words = phrase.split()
                if len(raw_words) <= len(phrase_words) + 2:
                    # Not enough non-phrase content; could be a real "thanks"
                    continue
                if normalized_full.endswith(phrase):
                    # Strip those trailing words from raw_words
                    new_words = raw_words[:-len(phrase_words)]
                    # Also strip any trailing punctuation token left dangling
                    while new_words and re.match(r"^[\W_]+$", new_words[-1]):
                        new_words.pop()
                    if new_words:
                        log.warning(
                            f"Hallucination: stripping trailing {phrase!r} "
                            f"({len(phrase_words)} words) - kept {len(new_words)} real words"
                        )
                        raw_words = new_words
                        raw_text = " ".join(raw_words)
                    break

        # ── Intra-word loop check ────────────────────────────────────────────
        # Catches hallucinations baked INTO a single token, e.g.
        # "CaitKatKatKat..." (no spaces) which the word-level n-gram guard
        # below misses entirely because text.split() returns a single element.
        # Strategy: regex-match a 2-8 char substring that repeats 5+ times
        # consecutively. Keep whatever prefix preceded the loop, drop the rest.
        _INTRA_LOOP_RE = re.compile(r"(.{2,8}?)\1{4,}")
        cleaned_words = []
        intra_stripped = 0
        for w in raw_words:
            if len(w) < 30:
                # Short tokens can't be a meaningful loop; keep as-is
                cleaned_words.append(w)
                continue
            m = _INTRA_LOOP_RE.search(w)
            if not m:
                cleaned_words.append(w)
                continue
            # Found a loop within this word. Compute what to keep.
            loop_start = m.start()
            loop_end   = m.end()
            substr     = m.group(1)
            reps       = (loop_end - loop_start) // len(substr)
            prefix     = w[:loop_start]
            suffix     = w[loop_end:]
            log.warning(
                f"Hallucination: intra-word loop in {w[:60]!r}... "
                f"({substr!r} repeats {reps}x at pos {loop_start} of {len(w)}) — stripping"
            )
            intra_stripped += (loop_end - loop_start)
            # Keep prefix. For the suffix: if it's short relative to the loop
            # pattern, it's almost certainly an incomplete cycle leftover (e.g.
            # 'tKa' repeating with one trailing 't') - drop it. If it's
            # substantially longer than the pattern, treat it as real content
            # that came after the loop and keep it with a space separator.
            if suffix and len(suffix) > len(substr) * 2:
                kept = (prefix + " " + suffix).strip()
            else:
                kept = prefix.strip()
            if len(kept) >= 1:
                cleaned_words.append(kept)
        if intra_stripped > 0:
            raw_words = cleaned_words
            raw_text = " ".join(raw_words)
            if not raw_text.strip():
                log.warning("Hallucination: nothing left after intra-word strip — discarding")
                _show_no_speech()
                return
            log.info(f"Intra-word strip recovered: {raw_text!r}")

        if len(raw_words) >= 6:
            # Consecutive-run check with stripping.
            # Catches partial loops that are interleaved with real content,
            # e.g. "I plan to send a note... Thank you. Thank you. Thank you..."
            # Instead of discarding the whole transcription, we locate the
            # repeat run, strip it, and keep the legitimate prefix/suffix.
            # Thresholds: window=1 needs 8 consecutive repeats (legitimate
            # emphatic speech like "no no no no no" shouldn't trigger).
            # Windows 2..5 need 5 consecutive repeats.
            best = None   # (window, run_start, run_end, run_length, gram_text)
            for window in (1, 2, 3, 4, 5):
                if len(raw_words) < window * 5 + 1:
                    continue
                threshold = 8 if window == 1 else 5
                max_run = 1
                max_run_start = None
                max_run_end = None
                max_run_gram = None
                run = 1
                run_start = None
                for i in range(window, len(raw_words) - window + 1):
                    prev_gram = tuple(raw_words[i - window:i])
                    this_gram = tuple(raw_words[i:i + window])
                    if prev_gram == this_gram:
                        if run == 1:
                            run_start = i - window
                        run += 1
                        if run > max_run:
                            max_run = run
                            max_run_start = run_start
                            max_run_end = i + window    # exclusive end of matched content
                            max_run_gram = this_gram
                    else:
                        run = 1
                if max_run >= threshold and max_run_start is not None:
                    if best is None or max_run > best[3]:
                        best = (window, max_run_start, max_run_end, max_run, max_run_gram)

            if best is not None:
                window, run_start, run_end, run_length, offending = best
                run_end = min(run_end, len(raw_words))
                prefix = raw_words[:run_start]
                suffix = raw_words[run_end:]
                cleaned = prefix + suffix
                # Keep anything with 2+ real words; otherwise nothing substantial
                # survived the strip and the whole thing is junk.
                if len(cleaned) < 2:
                    log.warning(
                        f"Hallucination detected: {window}-gram {' '.join(offending)!r} "
                        f"repeats {run_length}x; nothing left after strip — discarding"
                    )
                    _show_no_speech()
                    return
                stripped_count = len(raw_words) - len(cleaned)
                log.warning(
                    f"Hallucination: {window}-gram {' '.join(offending)!r} repeats "
                    f"{run_length}x at position {run_start} — stripped {stripped_count} words, "
                    f"keeping {len(cleaned)} real words"
                )
                raw_words = cleaned
                raw_text = " ".join(raw_words)

        # ── Early-path COMMAND mode: try to classify raw ASR as a command ─
        # This MUST happen BEFORE spoken-punctuation, because several
        # command phrases ("new paragraph", "new line") are ALSO spoken-
        # punctuation rules. If we ran spoken-punct first, "New paragraph"
        # would be replaced with "\n\n" and become empty, and the classifier
        # would see nothing.
        # Fires when either:
        #   - sticky _command_mode is on, or
        #   - one-shot was triggered via Shift+Alt+C for just this utterance.
        early_command_fired = False
        if _command_mode or _one_shot_command:
            try:
                import commands as _cmds_early
                early_cmd = _cmds_early.classify(raw_text, has_selection=False)
                if early_cmd is not None and early_cmd.source == "regex":
                    # Only trust regex matches here - LLM classification needs
                    # the fuller pipeline context (selection, screen_ctx) which
                    # we haven't captured yet. LLM path runs later in the
                    # normal flow after dictionary substitution.
                    log.info(f"[Mode=COMMAND] early regex match: {early_cmd.type} <- {raw_text!r}")
                    # Save to history so user sees what was said
                    _last_transcription = raw_text
                    new_entry = {
                        "text":   f"[CMD:{early_cmd.type}] {raw_text}",
                        "raw":    raw_text,
                        "ts":     datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "engine": f"{_current_engine}/{_current_model}",
                    }
                    threading.Thread(target=_save_history, args=(new_entry,),
                                     daemon=True, name="save-history").start()
                    ok = _cmds_early.execute(early_cmd, selection_text="", kb=keyboard)
                    if ok:
                        log.info(f"[Mode=COMMAND] ✓ executed ({time.perf_counter() - t0:.2f}s)")
                        if _widget:
                            _widget.set_state("done")
                        return
                    log.warning("[Mode=COMMAND] early-path execution failed; falling through")
            except Exception as e:
                log.warning(f"[Mode=COMMAND] early classifier error: {e}")

        # ── Spoken punctuation ───────────────────────────────────────────
        # Replace spoken words ("period", "comma", "new line", …) with symbols
        # BEFORE LLM cleanup so the LLM sees clean punctuated text.
        punct_text = _apply_spoken_punctuation(raw_text)
        if punct_text != raw_text:
            log.info(f"Spoken punct: {punct_text!r}")
        final_text = punct_text

        # ── LLM cleanup (optional) ────────────────────────────────────────
        # Routes through llm_provider, which dispatches to local Ollama or
        # any OpenAI-compatible endpoint based on llm_provider config.
        # Returns None on any failure - we keep the raw transcript in that case.
        if _post_process:
            try:
                from llm_provider import llm_call
                t_llm = time.perf_counter()
                cleaned = llm_call(
                    CLEANUP_USER_TEMPLATE.format(transcript=raw_text),
                    system_prompt=CLEANUP_SYSTEM_PROMPT,
                    temperature=0.1,
                    max_tokens=512,
                    timeout=30.0,
                )
                if cleaned:
                    final_text = cleaned
                    log.info(f"LLM ({time.perf_counter() - t_llm:.2f}s): {final_text!r}")
                else:
                    log.info("LLM cleanup returned nothing - keeping raw transcript")
            except Exception as e:
                log.warning(f"LLM cleanup skipped: {e}")

        # ── Personal dictionary substitution ─────────────────────────────
        final_text = _apply_dictionary(final_text)
        if final_text != raw_text:
            log.info(f"Dictionary applied: {final_text!r}")

        # ── COMMAND mode: classify & execute ─────────────────────────────
        # In PURE mode this block is skipped entirely (zero overhead).
        # In COMMAND mode the utterance is routed through a hybrid regex+LLM
        # classifier. Commands are executed directly; non-commands fall through
        # to the normal paste path as dictation.
        # Also fires for one-shot command mode (Shift+Alt+C).
        if _command_mode or _one_shot_command:
            try:
                import context as _ctx
                import commands as _cmds
                field_ctx = _ctx.get_field_context()
                # v2.3: capture screen OCR context when enabled. Only runs
                # when COMMAND mode is on and user has opted in. Fully local.
                screen_ctx = ""
                if _use_screen_context:
                    try:
                        t_ocr = time.perf_counter()
                        screen_ctx = _ctx.capture_screen_context()
                        if screen_ctx:
                            log.info(f"[ScreenContext] captured {len(screen_ctx)} chars in {time.perf_counter() - t_ocr:.2f}s")
                    except Exception as e:
                        log.debug(f"[ScreenContext] capture failed: {e}")
                cmd = _cmds.classify(
                    final_text,
                    has_selection=field_ctx.has_selection,
                    screen_context=screen_ctx,
                )
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
        #
        # NOTE: we no longer check `_bg_asr_model is not None` here. The v2.5.1
        # idle-unload supervisor may have dropped the bg model, but _run_bg_asr
        # has its own reload-on-demand path. Gating here would silently disable
        # two-pass after the first idle period - same class of bug we just
        # fixed in _start_recording.
        if _two_pass_enabled and _current_engine == "moonshine":
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
        # Always clear the one-shot flag regardless of what happened. Whether
        # the command executed, dictated as normal, or errored out, the user
        # expects to return to PURE behavior for the next utterance.
        if _one_shot_command:
            log.info("[OneShot] command processed, reverting to PURE")
            _one_shot_command = False
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
        # Two distinct cases that both look like "_asr_model is None":
        #   1. App just started, model is still loading for the first time.
        #      User has to wait - refuse the start.
        #   2. Model was loaded successfully earlier, then the idle-unload
        #      supervisor dropped the reference to save RAM. We can start
        #      recording immediately; `_run_asr` will reload before transcribing.
        # `_last_asr_use_time > 0` is the discriminator - it only gets set
        # after at least one successful transcription.
        if _last_asr_use_time > 0:
            log.info("[IdleUnload] model unloaded earlier - will reload during transcription")
            # Fall through: allow recording to proceed
        else:
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
    "enter", "z", "r", "c", "t", "space",
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

    # ── Shift+Alt+R — retroactive capture (last ~15 s) ────────────────────────
    # Shift+Alt+R chosen for consistency with Shift+Alt+Z (re-paste) and because
    # Ctrl+Win+B collides with Intel/Lenovo display drivers on some systems.
    if key == "r":
        if down and _alt_down and _shift_down:
            threading.Thread(target=_trigger_retro_capture,
                             daemon=True, name="retro").start()
            return

    # ── Shift+Alt+T — re-transcribe last ("Try again") ───────────────────────
    # Re-runs ASR on the most recently captured audio with the current engine.
    # Useful when a transcription looped (CaitKatKat...) or came out garbled.
    # For a different model, use right-click -> "Re-transcribe last" cascade.
    if key == "t":
        if down and _alt_down and _shift_down:
            threading.Thread(target=lambda: _retranscribe_last("", ""),
                             daemon=True, name="retranscribe-hotkey").start()
            return

    # ── Shift+Alt+C — one-shot COMMAND mode ──────────────────────────────────
    # Press once: begin hands-free recording with the command flag set so the
    # classifier fires on what you say. Press again: stop, classify, execute,
    # then auto-revert to PURE mode. No toggle management required.
    if key == "c":
        if down and _alt_down and _shift_down:
            threading.Thread(target=_trigger_one_shot_command,
                             daemon=True, name="oneshot-cmd").start()
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


def _trigger_one_shot_command():
    """Shift+Alt+C: one-shot COMMAND mode.

    First press → start hands-free recording AND set the one-shot flag, so
    whatever the user says this round will be run through the command
    classifier regardless of the current sticky mode.
    Second press → stop and send. _transcribe_and_paste sees the one-shot
    flag, classifies + executes, and resets the flag on its way out.

    Key insight: this collapses "switch to COMMAND mode" and "start recording"
    into a single gesture, then auto-reverts so the user never has to manage
    mode state. The sticky `_command_mode` toggle is untouched."""
    global _one_shot_command
    if _processing:
        log.info("[OneShot] ignored (processing)")
        return
    if _recording:
        # Second press — stop and let the pipeline run
        log.info("[OneShot] stopping recording; command will fire on release")
        _stop_and_send()
        return
    # First press — start recording, mark this round as one-shot command
    _one_shot_command = True
    log.info("[OneShot] listening for one command...")
    _toggle_hands_free()

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    global _widget, _tray, _stream, _asr_model

    # Per-Monitor V2 DPI awareness — call BEFORE any Tk root is created.
    # Without this, a Toplevel (like the hover card) rendered on a secondary
    # monitor with different DPI scaling comes out blurry or wrong-sized.
    # Swallow the error on older Windows where shcore is unavailable; the
    # app still works, just without per-monitor DPI correctness.
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        log.info("startup: per-monitor V2 DPI awareness enabled")
    except Exception as e:
        log.debug(f"startup: DPI awareness unavailable ({e}); continuing")

    # Brand the taskbar: declare a distinct AppUserModelID so any window we
    # show uses our icon and groups under "Cait Whisper" instead of generic
    # "python"/"pythonw". Set before any window is created.
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Cait.Whisper")
    except Exception:
        pass

    log.info("startup: loading history and dictionary")
    _load_history()
    _load_dictionary()

    # ── Widget first — appears immediately ────────────────────────────────────
    log.info("startup: creating widget")
    _widget = StatusWidget()
    # Now that a Tk root exists, ask theme to upgrade font choices if
    # brand-preferred families (Inter, Inter Tight, etc.) are installed.
    # Idempotent and silent if not.
    theme.resolve_fonts()
    log.info("startup: widget visible")

    # ── Startup splash ────────────────────────────────────────────────────────
    # A centered brand splash while the model loads. The coin stays quiet
    # (idle) in the corner so there aren't two loading animations; the splash
    # owns the "we're warming up" moment. Most valuable on first launch, when
    # the model is downloaded (~a minute) and the user needs reassurance.
    # finish() is guaranteed: on ready, on error, and via a safety timeout.
    global _splash
    try:
        _splash = _splash_mod.SplashScreen(_widget.root)
        _splash.set_status("Preparing speech model...")
    except Exception as e:
        _splash = None
        log.debug(f"startup: splash unavailable ({e}); continuing")

    def _close_splash():
        global _splash
        if _splash is not None:
            try:
                _splash.finish()
            except Exception:
                pass
            _splash = None

    # Safety net: never let the splash trap the user, even if the model load
    # hangs or the connection is slow. The coin (quiet idle) is already there.
    _widget.root.after(120_000, _close_splash)

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
    # Try the configured device first; if it fails (disconnected, exclusive
    # locked by another app, sample-rate mismatch), automatically fall back
    # to system default rather than crashing the whole app at startup.
    log.info("startup: opening mic stream")

    def _try_open_stream(device_idx, label):
        return sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            callback=_audio_callback,
            blocksize=1024,
            device=device_idx,
        )

    _stream_opened = False
    if INPUT_DEVICE:
        _device_idx = _resolve_input_device(INPUT_DEVICE)
        log.info(f"startup: trying configured input device {INPUT_DEVICE!r} -> index={_device_idx}")
        try:
            _stream = _try_open_stream(_device_idx, INPUT_DEVICE)
            _stream.start()
            _stream_opened = True
            log.info("startup: mic stream OK (configured device)")
        except Exception as e:
            log.warning(
                f"startup: configured device {INPUT_DEVICE!r} failed to open ({e}); "
                f"falling back to system default. Device may be disconnected, "
                f"exclusive-locked by another app, or have incompatible sample rate."
            )

    if not _stream_opened:
        try:
            log.info("startup: opening system default input device")
            _stream = _try_open_stream(None, "system default")
            _stream.start()
            log.info("startup: mic stream OK (system default)")
        except Exception as e:
            _fatal(
                f"Could not open microphone: {e}\n\n"
                f"Check that a microphone is connected and not in use by another app.",
                e,
            )

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
            # Close the splash before the fatal dialog so it doesn't linger.
            _ui_after(0, _close_splash)
            _ui_after(0, lambda: _fatal(f"Failed to load ASR model: {e}", e))
            return
        # Transition to idle and play the ready beeps — all on the main thread
        def _on_ready():
            _close_splash()                  # splash done; coin takes over
            _widget.set_state("idle")
            # Coral flash on the coin for 2 s — subtle "model is ready" signal
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

    # ── Idle-unload supervisor (v2.5.1 lean mode) ─────────────────────────────
    # Watches the last-use timestamps and drops ASR model references after
    # configurable idle thresholds. Reload is automatic on next use.
    threading.Thread(target=_idle_unload_supervisor,
                     daemon=True, name="idle-unload").start()

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
