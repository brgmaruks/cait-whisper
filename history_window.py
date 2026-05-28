"""
cait-whisper  ·  History & Dictionary window
Standalone process — fully decoupled from the main transcription widget.
Reads / writes history.json, dictionary.json, and pending_corrections.json
in the same directory.  Auto-refreshes when the files change on disk.
"""

import ctypes
import json
import os
import sys
import time
import tkinter as tk
from pathlib import Path

# Per-Monitor V2 DPI awareness must be set BEFORE any Tk root is created,
# otherwise tabs and widgets render blurry on secondary monitors with
# different scaling. Silent no-op on Windows versions without shcore.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

try:
    import pyperclip
except ImportError:
    pyperclip = None

# ─── Paths ────────────────────────────────────────────────────────────────────
_DIR          = Path(__file__).parent
_HISTORY_PATH = _DIR / "history.json"
_DICT_PATH    = _DIR / "dictionary.json"
_PENDING_PATH = _DIR / "pending_corrections.json"
_LOG_PATH     = _DIR / "cait-whisper.log"
_MAX_HISTORY  = 50

# ─── Logging — share the main client's log file ───────────────────────────────
# history_window runs as a separate Python process. Without this, any log.*
# call inside modules it imports (llm_provider, config_io) goes to stderr
# and is invisible. We attach the same rotating file handler that client.py
# configured so debug traces from provider test_connection etc. show up in
# cait-whisper.log alongside the main client's output.
import logging
import logging.handlers
if not logging.getLogger("cait-whisper").handlers:
    _log_handler = logging.handlers.RotatingFileHandler(
        _LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8",
    )
    _log_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] [history_window] %(message)s",
    ))
    _log = logging.getLogger("cait-whisper")
    _log.addHandler(_log_handler)
    _log.setLevel(logging.INFO)

# ─── Theme ────────────────────────────────────────────────────────────────────
# All tokens come from theme.py - the single source of truth for cait-whisper's
# visual language. Local aliases (_BG, _FG, ...) keep older tab code short
# without requiring every font=() tuple to change. New code should prefer the
# underscore-free names (theme.BG, theme.FG) directly.
import theme
_BG      = theme.BG
_BG_SUB  = theme.BG_SUBTLE
_FG      = theme.FG
_FG_MUTED = theme.FG_MUTED
_DIM     = theme.FG_DIM
_ACC     = theme.ACCENT
_ACC_HOV = theme.ACCENT_HOVER
_EBGD    = theme.BG_ELEVATED
# State colors (used by toasts and test-connection status)
_SUCCESS = theme.SUCCESS
_WARNING = theme.WARNING
_INFO    = theme.INFO
_DANGER  = theme.DANGER

# ─── Data helpers ─────────────────────────────────────────────────────────────

def _load_history() -> list[dict]:
    try:
        if _HISTORY_PATH.exists():
            return json.loads(_HISTORY_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[cait-whisper] Could not load history: {e}", file=sys.stderr)
    return []


def _atomic_write(path: Path, data):
    """Write JSON atomically via temp-file + rename to avoid half-written reads."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)  # atomic rename on same filesystem


def _save_history(history: list[dict]):
    try:
        _atomic_write(_HISTORY_PATH, history[-_MAX_HISTORY:])
    except Exception as e:
        print(f"[cait-whisper] Could not save history: {e}", file=sys.stderr)


def _load_dict() -> dict[str, str]:
    try:
        if _DICT_PATH.exists():
            return json.loads(_DICT_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[cait-whisper] Could not load dictionary: {e}", file=sys.stderr)
    return {}


def _save_dict(dictionary: dict[str, str]):
    try:
        _atomic_write(_DICT_PATH, dict(sorted(dictionary.items())))
    except Exception as e:
        print(f"[cait-whisper] Could not save dictionary: {e}", file=sys.stderr)


def _load_pending() -> dict[str, dict]:
    """Load pending_corrections.json — { "heard→correct": {"count": N} }"""
    try:
        if _PENDING_PATH.exists():
            return json.loads(_PENDING_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[cait-whisper] Could not load pending corrections: {e}", file=sys.stderr)
    return {}


def _save_pending(pending: dict[str, dict]):
    try:
        _atomic_write(_PENDING_PATH, pending)
    except Exception as e:
        print(f"[cait-whisper] Could not save pending corrections: {e}", file=sys.stderr)


def _file_mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except Exception:
        return 0.0


# ─── Window ───────────────────────────────────────────────────────────────────

class HistoryDictWindow:
    def __init__(self):
        self.root = tk.Tk()
        # OS window title bar shows plain text - styling not possible at
        # the Windows level. Use the full product wordmark so taskbar and
        # Alt-Tab show "Cait. whisper".
        self.root.title("Cait. whisper")
        self.root.resizable(True, True)
        # v2.5.3: 540 -> 640 wide. The four tab labels (Recent transcriptions,
        # Dictionary, Pending, Settings) PLUS the new coral glyphs need more
        # room than 540 to lay out without crowding. Height stays at 680 with
        # a small bump from 640 for the heavier title bar.
        self.root.geometry("640x680")
        self.root.configure(bg=_BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Apply the brand .ico so the title bar, taskbar, and Alt-Tab show
        # the Φ-in-circle instead of Tk's default feather. The file is
        # generated on first launch by client.py via theme.ensure_brand_ico.
        try:
            from pathlib import Path
            ico = Path(__file__).parent / "assets" / "cait.ico"
            if not ico.exists():
                theme.ensure_brand_ico(ico)
            self.root.iconbitmap(default=str(ico))
        except Exception as e:
            print(f"[cait-whisper] could not set window icon: {e}", file=sys.stderr)

        # DWM rounded corners (Windows 11)
        try:
            import ctypes
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(ctypes.c_int(2)), 4)
        except Exception:
            pass

        self._history:    list[dict]       = _load_history()
        self._dictionary: dict[str, str]   = _load_dict()
        self._pending:    dict[str, dict]  = _load_pending()
        self._embedded_widgets: list[tk.Widget] = []   # tracked for cleanup
        self._hist_mtime    = _file_mtime(_HISTORY_PATH)
        self._dict_mtime    = _file_mtime(_DICT_PATH)
        self._pending_mtime = _file_mtime(_PENDING_PATH)

        self._build_ui()

        # Poll for file changes every 1.5 seconds
        self._poll_files()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Brand title strip: PIL-rendered Phi-in-circle mark + BOLD "Cait"
        # wordmark + coral italic period. The lockup reads as the brand
        # identity, with the wordmark style matching every other "Cait"
        # surface in the app.
        bar = tk.Frame(self.root, bg=_BG)
        bar.pack(fill="x", padx=14, pady=(12, 4))

        # Brand mark: anti-aliased PIL render, stored as a PhotoImage on
        # the instance so it doesn't get garbage-collected.
        self._title_mark_photo = theme.get_mark_photo(
            26, border_color=theme.CORAL,
            glyph_color=theme.CORAL, fill_color=_BG,
        )
        mark_lbl = tk.Label(bar, image=self._title_mark_photo, bg=_BG,
                            borderwidth=0, highlightthickness=0)
        mark_lbl.pack(side="left", padx=(0, 10))

        # Brand lockup: "Cait. whisper" - bold + coral italic period +
        # italic whisper. Centralized in theme.brand_lockup so every
        # surface renders identically.
        theme.brand_lockup(bar, bg=_BG, fg=_FG,
                           cait_size=15, period_size=17,
                           whisper_size=15).pack(side="left")

        # Close button uses the custom close glyph so it matches the
        # other inline icons everywhere else in this window.
        self._close_glyph_photo = theme.get_glyph_photo("close", 14, _DIM)
        tk.Button(bar, image=self._close_glyph_photo, bg=_BG, bd=0,
                  activebackground=_BG, cursor="hand2",
                  command=self._on_close).pack(side="right")

        # Tab bar - each tab gets a coral brand glyph next to its label so
        # the navigation has its own visual rhythm and matches the brand
        # language everywhere else. Glyphs are cached PhotoImages we keep
        # alive on the instance so they don't get garbage-collected.
        self._tab_var = tk.StringVar(value="history")
        tab_bar = tk.Frame(self.root, bg=_BG)
        tab_bar.pack(fill="x", padx=14)

        tab_specs = [
            ("transcripts", "Recent",     "history"),
            ("dictionary",  "Dictionary", "dict"),
            ("pending",     "Pending",    "pending"),
            ("settings",    "Settings",   "settings"),
        ]
        self._tab_glyph_photos: dict = {}
        for glyph_name, label, key in tab_specs:
            photo = theme.get_glyph_photo(glyph_name, 14, theme.CORAL)
            self._tab_glyph_photos[key] = photo
            tk.Radiobutton(
                tab_bar, text=label, image=photo, compound="left",
                variable=self._tab_var, value=key,
                bg=_BG, fg=_FG, selectcolor=_EBGD,
                activebackground=_BG, font=("Segoe UI", 9),
                indicatoron=False, padx=10, pady=5, bd=0, relief="flat",
                command=self._switch_tab,
            ).pack(side="left", padx=(0, 4))

        tk.Frame(self.root, bg=_DIM, height=1).pack(fill="x", padx=14, pady=(4, 0))

        self._build_history_tab()
        self._build_dict_tab()
        self._build_pending_tab()
        self._build_settings_tab()
        self._hist_frame.pack(fill="both", expand=True, padx=12, pady=8)

    # ── Scrollable text helper ────────────────────────────────────────────────

    @staticmethod
    def _bind_scroll(widget):
        def _on_wheel(e):
            widget.yview_scroll(-1 * (e.delta // 120), "units")
        widget.bind("<Enter>", lambda e: widget.bind("<MouseWheel>", _on_wheel))
        widget.bind("<Leave>", lambda e: widget.unbind("<MouseWheel>"))

    def _make_text(self, parent) -> tk.Text:
        sb = tk.Scrollbar(parent, orient="vertical", bg=_DIM,
                          troughcolor=_EBGD, bd=0, width=8)
        sb.pack(side="right", fill="y")
        t = tk.Text(
            parent, bg=_BG, fg=_FG,
            font=("Segoe UI", 9), bd=0, padx=10, pady=6,
            wrap="word", yscrollcommand=sb.set, state="disabled",
            cursor="arrow", relief="flat", spacing1=1, spacing3=1,
            selectbackground=_ACC,
        )
        sb.config(command=t.yview)
        t.pack(side="left", fill="both", expand=True)
        t.tag_config("meta", foreground=_DIM, font=("Segoe UI", 7))
        t.tag_config("body", foreground=_FG,  font=("Segoe UI", 9))
        t.tag_config("dim",  foreground=_DIM, font=("Segoe UI", 9))
        self._bind_scroll(t)
        return t

    # ── History tab ───────────────────────────────────────────────────────────

    def _build_history_tab(self):
        self._hist_frame = tk.Frame(self.root, bg=_BG)

        # ── Toolbar: search + clear ───────────────────────────────────────────
        tb = tk.Frame(self._hist_frame, bg=_BG)
        tb.pack(fill="x", pady=(0, 4))

        # Search icon: custom coral magnifier glyph, replaces the system
        # 🔍 emoji which renders inconsistently across Windows fonts.
        self._search_glyph_photo = theme.get_glyph_photo("search", 14, theme.CORAL)
        tk.Label(tb, image=self._search_glyph_photo, bg=_BG,
                 borderwidth=0, highlightthickness=0,
                 ).pack(side="left", padx=(0, 6))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._populate_history())
        search_entry = tk.Entry(
            tb, textvariable=self._search_var,
            bg=_EBGD, fg=_FG, insertbackground=_FG,
            font=("Segoe UI", 9), width=20, bd=0, relief="flat",
        )
        search_entry.pack(side="left", ipady=3)

        # Clear-search button: custom close glyph, muted color
        def _clear_search():
            self._search_var.set("")
            search_entry.focus_set()
        self._clear_search_photo = theme.get_glyph_photo("close", 11, _DIM)
        tk.Button(tb, image=self._clear_search_photo, bg=_BG, bd=0,
                  activebackground=_BG, cursor="hand2",
                  command=_clear_search,
                  ).pack(side="left", padx=(2, 8))

        # Clear-all button: keep as text since "Clear all" is the affordance
        tk.Button(tb, text="Clear all", bg=_EBGD, fg=_DIM, bd=0,
                  font=("Segoe UI", 8), activebackground=_BG,
                  cursor="hand2", command=self._clear_all_history,
                  ).pack(side="right", padx=2)

        self._hist_text = self._make_text(self._hist_frame)
        self._populate_history()

    def _destroy_embedded(self):
        """Destroy all tracked embedded widgets (buttons inside Text widgets)."""
        for w in self._embedded_widgets:
            try:
                w.destroy()
            except Exception:
                pass
        self._embedded_widgets.clear()

    def _populate_history(self):
        self._destroy_embedded()
        t = self._hist_text
        t.config(state="normal")
        t.delete("1.0", "end")

        query = self._search_var.get().strip().lower() if hasattr(self, "_search_var") else ""
        items = list(reversed(self._history))

        # Filter by search query (case-insensitive substring match)
        if query:
            items = [it for it in items if query in it.get("text", "").lower()]

        if not items:
            msg = (f'\n  No results for \u201c{query}\u201d.\n' if query else "\n  No transcriptions yet.\n")
            t.insert("end", msg, "dim")
            t.config(state="disabled")
            return

        for i, item in enumerate(items):
            ts     = item.get("ts", "")
            engine = item.get("engine", "")
            text   = item.get("text", "")
            # Map back to original index in self._history for deletion
            orig_idx = len(self._history) - 1 - self._history[::-1].index(item) \
                       if item in self._history else -1
            bg  = _EBGD if i % 2 == 0 else _BG
            tag = f"row{i}"
            t.tag_config(tag, background=bg)

            # Delete button: custom close glyph in muted color
            del_photo = theme.get_glyph_photo("close", 11, _DIM)
            del_btn = tk.Button(
                t, image=del_photo, bg=bg, bd=0,
                activebackground=bg, cursor="hand2",
                command=(lambda idx=orig_idx: self._delete_history_item(idx)),
            )
            del_btn._photo = del_photo   # keep reference alive
            t.window_create("end", window=del_btn, padx=4, pady=2)
            self._embedded_widgets.append(del_btn)

            # Copy button: custom copy glyph in coral (brand action color)
            if pyperclip:
                cp_photo = theme.get_glyph_photo("copy", 13, _ACC)
                cp_btn = tk.Button(
                    t, image=cp_photo, bg=bg, bd=0,
                    activebackground=bg, cursor="hand2",
                    command=(lambda tx=text: pyperclip.copy(tx)),
                )
                cp_btn._photo = cp_photo
                t.window_create("end", window=cp_btn, padx=4, pady=2)
                self._embedded_widgets.append(cp_btn)

            t.insert("end", f" {ts}  \u00b7  {engine}\n", ("meta", tag))
            t.insert("end", f"  {text}\n", ("body", tag))

        t.config(state="disabled")
        # FEAT-6: Auto-scroll to top so newest entry (first in reversed list) is always visible
        t.see("1.0")

    def _delete_history_item(self, idx: int):
        if 0 <= idx < len(self._history):
            self._history.pop(idx)
            _save_history(self._history)
            self._hist_mtime = _file_mtime(_HISTORY_PATH)
            self._populate_history()

    def _clear_all_history(self):
        self._history.clear()
        _save_history(self._history)
        self._hist_mtime = _file_mtime(_HISTORY_PATH)
        self._populate_history()

    # ── Dictionary tab ────────────────────────────────────────────────────────

    def _build_dict_tab(self):
        self._dict_frame = tk.Frame(self.root, bg=_BG)

        add_row = tk.Frame(self._dict_frame, bg=_BG)
        add_row.pack(fill="x", pady=(0, 6))
        tk.Label(add_row, text="Heard:", bg=_BG, fg=_FG,
                 font=("Segoe UI", 9)).pack(side="left")
        self._e_from = tk.Entry(add_row, bg=_EBGD, fg=_FG,
                                insertbackground=_FG,
                                font=("Segoe UI", 9), width=12, bd=0)
        self._e_from.pack(side="left", padx=(4, 8))
        # Custom coral arrow glyph in place of the Unicode \u2192
        self._dict_arrow_photo = theme.get_glyph_photo("arrow_right", 14, theme.CORAL)
        tk.Label(add_row, image=self._dict_arrow_photo, bg=_BG,
                 borderwidth=0, highlightthickness=0,
                 ).pack(side="left", padx=(0, 4))
        tk.Label(add_row, text="Replace with:", bg=_BG, fg=_FG,
                 font=("Segoe UI", 9)).pack(side="left")
        self._e_to = tk.Entry(add_row, bg=_EBGD, fg=_FG,
                              insertbackground=_FG,
                              font=("Segoe UI", 9), width=12, bd=0)
        self._e_to.pack(side="left", padx=4)
        tk.Button(add_row, text="Add", bg=_ACC, fg="#000", bd=0,
                  font=("Segoe UI", 8, "bold"), padx=6,
                  command=self._add_dict_entry).pack(side="left", padx=4)

        tk.Frame(self._dict_frame, bg=_DIM, height=1).pack(fill="x", pady=(0, 6))

        self._dict_text = self._make_text(self._dict_frame)
        self._populate_dict()

    def _populate_dict(self):
        self._destroy_embedded()
        t = self._dict_text
        t.config(state="normal")
        t.delete("1.0", "end")
        if not self._dictionary:
            t.insert("end",
                     "\n  No dictionary entries yet.\n"
                     "  Words learned automatically appear here.\n", "dim")
            t.config(state="disabled")
            return
        for i, (k, v) in enumerate(sorted(self._dictionary.items())):
            bg  = _EBGD if i % 2 == 0 else _BG
            tag = f"drow{i}"
            t.tag_config(tag, background=bg)

            del_photo = theme.get_glyph_photo("close", 11, _DIM)
            btn = tk.Button(
                t, image=del_photo, bg=bg, bd=0,
                activebackground=bg, cursor="hand2",
                command=(lambda key=k: self._del_dict_entry(key)),
            )
            btn._photo = del_photo
            t.window_create("end", window=btn, padx=4, pady=3)
            self._embedded_widgets.append(btn)
            t.insert("end", f"  {k}  \u2192  {v}\n", ("body", tag))
        t.config(state="disabled")

    def _add_dict_entry(self):
        k = self._e_from.get().strip().lower()
        v = self._e_to.get().strip()
        if not k or not v:
            return
        self._dictionary[k] = v
        _save_dict(self._dictionary)
        self._dict_mtime = _file_mtime(_DICT_PATH)
        self._e_from.delete(0, "end")
        self._e_to.delete(0, "end")
        self._populate_dict()

    def _del_dict_entry(self, key: str):
        self._dictionary.pop(key, None)
        _save_dict(self._dictionary)
        self._dict_mtime = _file_mtime(_DICT_PATH)
        self._populate_dict()

    # ── Pending corrections tab ───────────────────────────────────────────────

    def _build_pending_tab(self):
        self._pending_frame = tk.Frame(self.root, bg=_BG)

        tb = tk.Frame(self._pending_frame, bg=_BG)
        tb.pack(fill="x", pady=(0, 4))
        tk.Label(tb, text="Corrections seen but not yet promoted (need 2 total)",
                 bg=_BG, fg=_DIM, font=("Segoe UI", 8)).pack(side="left")
        tk.Button(tb, text="Clear all", bg=_EBGD, fg=_DIM, bd=0,
                  font=("Segoe UI", 8), activebackground=_BG,
                  cursor="hand2", command=self._clear_all_pending,
                  ).pack(side="right", padx=2)

        tk.Frame(self._pending_frame, bg=_DIM, height=1).pack(fill="x", pady=(0, 6))

        self._pending_text = self._make_text(self._pending_frame)
        self._populate_pending()

    def _populate_pending(self):
        self._destroy_embedded()
        t = self._pending_text
        t.config(state="normal")
        t.delete("1.0", "end")

        if not self._pending:
            t.insert("end",
                     "\n  No pending corrections.\n"
                     "  Make the same correction twice to see it here.\n", "dim")
            t.config(state="disabled")
            return

        for i, (key, data) in enumerate(sorted(self._pending.items())):
            count = data.get("count", 0)
            # key format: "heard→correct"
            parts = key.split("→", 1)
            heard   = parts[0] if len(parts) == 2 else key
            correct = parts[1] if len(parts) == 2 else "?"
            bg  = _EBGD if i % 2 == 0 else _BG
            tag = f"prow{i}"
            t.tag_config(tag, background=bg)

            # Delete button — removes from pending
            del_photo = theme.get_glyph_photo("close", 11, _DIM)
            del_btn = tk.Button(
                t, image=del_photo, bg=bg, bd=0,
                activebackground=bg, cursor="hand2",
                command=(lambda k=key: self._discard_pending(k)),
            )
            del_btn._photo = del_photo
            t.window_create("end", window=del_btn, padx=4, pady=2)
            self._embedded_widgets.append(del_btn)

            # Promote button — immediately add to dictionary
            promo_btn = tk.Button(
                t, text="Promote", bg=_ACC, fg="#000", bd=0,
                font=("Segoe UI", 7, "bold"), padx=4, activebackground=_ACC,
                cursor="hand2",
                command=(lambda k=key, h=heard, c=correct: self._promote_pending(k, h, c)),
            )
            t.window_create("end", window=promo_btn, padx=4, pady=2)
            self._embedded_widgets.append(promo_btn)

            t.insert("end",
                     f"  {heard}  \u2192  {correct}   "
                     f"({count}/2 corrections seen)\n",
                     ("body", tag))

        t.config(state="disabled")

    def _discard_pending(self, key: str):
        self._pending.pop(key, None)
        _save_pending(self._pending)
        self._pending_mtime = _file_mtime(_PENDING_PATH)
        self._populate_pending()

    def _promote_pending(self, key: str, heard: str, correct: str):
        """Immediately promote a pending correction to the dictionary."""
        # Add to dictionary
        self._dictionary[heard] = correct
        _save_dict(self._dictionary)
        self._dict_mtime = _file_mtime(_DICT_PATH)
        # Remove from pending
        self._pending.pop(key, None)
        _save_pending(self._pending)
        self._pending_mtime = _file_mtime(_PENDING_PATH)
        self._populate_pending()

    def _clear_all_pending(self):
        self._pending.clear()
        _save_pending(self._pending)
        self._pending_mtime = _file_mtime(_PENDING_PATH)
        self._populate_pending()

    # ── Settings tab ──────────────────────────────────────────────────────────
    # Profile-based LLM provider management (v2.5.0+). Users can save multiple
    # named profiles (Z.AI fast, Groq, local Ollama, etc.) with their own URLs,
    # models, and API keys. One profile is ACTIVE at a time; switching is a
    # single click. Adding a new profile pre-fills URL/model from a preset so
    # users don't have to memorize each provider's endpoint.

    def _build_settings_tab(self):
        from config_io import load_config, save_config
        from llm_provider import PROVIDER_PRESETS
        self._settings_load_config = load_config
        self._settings_save_config = save_config
        self._provider_presets = PROVIDER_PRESETS

        # Per-profile UI state (StringVars keyed by profile_id). Populated by
        # _render_profile_list each time profiles change.
        self._profile_ui_state: dict = {}   # id -> {"vars": {...}, "frame": Frame, "expanded": bool}

        self._settings_frame = tk.Frame(self.root, bg=_BG)

        # Sticky top bar: brand mark + title (with coral period) + status + save
        top = tk.Frame(self._settings_frame, bg=_BG)
        top.pack(fill="x", pady=(0, 8))

        # Brand mark: anti-aliased PIL render, kept alive on the instance.
        self._settings_mark_photo = theme.get_mark_photo(
            22, border_color=theme.CORAL,
            glyph_color=theme.CORAL, fill_color=_BG,
        )
        tk.Label(top, image=self._settings_mark_photo, bg=_BG,
                 borderwidth=0, highlightthickness=0,
                 ).pack(side="left", padx=(0, 8))

        # Heading + coral period (one per viewport rule)
        tk.Label(top, text="Settings", bg=_BG, fg=_ACC,
                 font=theme.t_title()).pack(side="left")
        tk.Label(top, text=".", bg=_BG, fg=theme.CORAL,
                 font=(theme.FONT_FAMILY_ITALIC, 16, "italic", "bold"),
                 padx=0, pady=0).pack(side="left")

        self._settings_status = tk.Label(top, text="", bg=_BG, fg=_DIM,
                                         font=theme.t_small())
        self._settings_status.pack(side="left", padx=(12, 0))
        tk.Button(top, text="Save", bg=_ACC, fg=_BG, bd=0,
                  font=theme.t_heading(), activebackground=theme.CORAL_SOFT,
                  cursor="hand2", padx=14, pady=3,
                  command=self._save_settings).pack(side="right")

        tk.Frame(self._settings_frame, bg=_DIM, height=1).pack(fill="x", pady=(0, 10))

        # Scrollable body
        body_canvas = tk.Canvas(self._settings_frame, bg=_BG, highlightthickness=0)
        body_canvas.pack(side="left", fill="both", expand=True)
        sb = tk.Scrollbar(self._settings_frame, orient="vertical",
                          command=body_canvas.yview)
        sb.pack(side="right", fill="y")
        body_canvas.config(yscrollcommand=sb.set)
        self._body_canvas = body_canvas
        body = tk.Frame(body_canvas, bg=_BG)
        body_canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>",
                  lambda e: body_canvas.config(scrollregion=body_canvas.bbox("all")))
        # Mouse wheel scroll for the settings body
        body_canvas.bind_all("<MouseWheel>",
                             lambda e: body_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"),
                             add="+")

        # ── LLM Providers section ──────────────────────────────────────
        self._section(body, "LLM Providers",
                      "Save as many provider profiles as you like (Z.AI fast, "
                      "Groq, OpenAI, your self-hosted Ollama, etc.). Switch "
                      "the active one with one click. Each profile keeps its "
                      "own API key so you never have to re-enter them.")

        # Container that holds profile cards; refreshed by _render_profile_list
        self._profiles_container = tk.Frame(body, bg=_BG)
        self._profiles_container.pack(fill="x", padx=12, pady=(0, 8))

        # Add-profile row: preset dropdown + button
        add_row = tk.Frame(body, bg=_BG)
        add_row.pack(fill="x", padx=12, pady=(4, 16))
        tk.Label(add_row, text="Add from preset:", bg=_BG, fg=_FG,
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 6))
        self._preset_var = tk.StringVar(value=self._provider_presets[0]["label"])
        preset_labels = [p["label"] for p in self._provider_presets]
        preset_menu = tk.OptionMenu(add_row, self._preset_var, *preset_labels)
        preset_menu.config(bg=_EBGD, fg=_FG, bd=0, activebackground=_EBGD,
                           font=("Segoe UI", 9), highlightthickness=0)
        preset_menu["menu"].config(bg=_EBGD, fg=_FG, bd=0,
                                   activebackground=_ACC, activeforeground=_BG)
        preset_menu.pack(side="left", padx=(0, 8))
        tk.Button(add_row, text="+ Add profile", bg=_ACC, fg=_BG, bd=0,
                  font=("Segoe UI", 9, "bold"), activebackground=_ACC,
                  cursor="hand2", padx=10, pady=3,
                  command=self._add_profile_from_preset).pack(side="left")

        # ── ASR Engine section (read-only display for now) ────────────
        self._section(body, "ASR Engine",
                      "Changeable from the right-click menu. Inline editing "
                      "arrives in a later release.")
        self._asr_engine_label = tk.Label(body, text="", bg=_BG, fg=_FG,
                                          font=("Consolas", 9), anchor="w",
                                          justify="left")
        self._asr_engine_label.pack(fill="x", padx=20, pady=(0, 6))

        # ── Features section (read-only display) ──────────────────────
        self._section(body, "Features",
                      "Toggle from the right-click menu. Saved to config "
                      "when changed.")
        self._features_label = tk.Label(body, text="", bg=_BG, fg=_FG,
                                        font=("Consolas", 9), anchor="w",
                                        justify="left")
        self._features_label.pack(fill="x", padx=20, pady=(0, 6))

        # ── Manual config access ──────────────────────────────────────
        self._section(body, "Manual config",
                      "Everything here is stored in config.json. Edit directly "
                      "if you need something the UI doesn't expose.")
        cfg_row = tk.Frame(body, bg=_BG)
        cfg_row.pack(fill="x", padx=20, pady=(0, 16))
        tk.Button(cfg_row, text="Open config.json", bg=_EBGD, fg=_FG, bd=0,
                  font=("Segoe UI", 9), activebackground=_BG,
                  cursor="hand2", padx=10, pady=3,
                  command=self._open_config_file).pack(side="left")

    def _section(self, parent, title, blurb):
        """Helper to render a section header + description.
        Brand pattern: bold heading + coral period (Playfair italic).
        Subdued blurb beneath."""
        tk.Frame(parent, bg=_DIM, height=1).pack(fill="x", pady=(8, 4), padx=8)
        # Heading row: title + coral period inline
        head = tk.Frame(parent, bg=_BG)
        head.pack(fill="x", padx=12, pady=(0, 2))
        tk.Label(head, text=title, bg=_BG, fg=_ACC,
                 font=theme.t_heading(), anchor="w").pack(side="left")
        tk.Label(head, text=".", bg=_BG, fg=theme.CORAL,
                 font=(theme.FONT_FAMILY_ITALIC, 13, "italic", "bold"),
                 padx=0, pady=0).pack(side="left")
        tk.Label(parent, text=blurb, bg=_BG, fg=_DIM,
                 font=("Segoe UI", 8), anchor="w", wraplength=620, justify="left",
                 ).pack(fill="x", padx=12, pady=(0, 6))

    # ── Profile model: read/write the v2.5.0 profile structure ───────

    def _load_profiles(self) -> tuple[dict, str]:
        """Return (profiles_dict, active_id). Migrates v2.4 / v2.5.0-beta
        flat-key configs into a one-profile dict on read.
        Profiles dict shape: {id: {label, type, base_url, model, api_key}}
        """
        cfg = self._settings_load_config()
        profiles = cfg.get("llm_profiles")
        active = cfg.get("llm_active_profile", "")
        if isinstance(profiles, dict) and profiles:
            # Already migrated
            if active not in profiles:
                active = next(iter(profiles))
            return profiles, active
        # Migrate: synthesize a single profile from whatever exists
        if cfg.get("llm_provider") == "openai_compatible":
            synth = {
                "label":    "Remote (migrated)",
                "type":     "openai_compatible",
                "base_url": cfg.get("llm_base_url", ""),
                "model":    cfg.get("llm_model") or "gpt-4o-mini",
                "api_key":  cfg.get("llm_api_key", ""),
            }
            return {"migrated": synth}, "migrated"
        # Default: one Local Ollama profile
        synth = {
            "label":    "Local Ollama",
            "type":     "local_ollama",
            "base_url": "",
            "model":    cfg.get("ollama_model", "llama3.2:3b"),
            "api_key":  "",
        }
        return {"local_ollama": synth}, "local_ollama"

    def _populate_settings(self):
        """Called when the tab is shown. Rebuilds the profile list + refreshes
        ASR/Features summaries from config."""
        try:
            cfg = self._settings_load_config()
        except Exception as e:
            self._settings_status.config(text=f"Could not read config: {e}", fg=_DANGER)
            return
        self._active_profile_id = cfg.get("llm_active_profile", "")
        profiles, active = self._load_profiles()
        self._profiles = profiles
        self._active_profile_id = active
        self._render_profile_list()

        # ASR + Features summaries
        engine = cfg.get("engine", "moonshine")
        model_key = {"moonshine": "moonshine_model",
                     "parakeet": "parakeet_model"}.get(engine, "whisper_model")
        self._asr_engine_label.config(
            text=(f"  Engine:   {engine}\n"
                  f"  Model:    {cfg.get(model_key, '?')}\n"
                  f"  Two-Pass: {cfg.get('two_pass', True)}")
        )
        feats = []
        for key, label in [
            ("auto_learn", "Auto-Learn"),
            ("spoken_punctuation", "Spoken Punctuation"),
            ("dev_logs", "Dev Logs"),
            ("use_screen_context", "Screen Context"),
            ("post_process", "LLM Cleanup"),
            ("command_mode", "Sticky COMMAND mode"),
        ]:
            mark = "ON " if cfg.get(key, False) else "OFF"
            feats.append(f"  {mark}  {label}")
        self._features_label.config(text="\n".join(feats))
        self._settings_status.config(text="", fg=_DIM)

    # ── Profile card rendering ───────────────────────────────────────

    def _render_profile_list(self):
        """Rebuild the profile-cards container from self._profiles."""
        # Clear old cards + UI state
        for child in self._profiles_container.winfo_children():
            child.destroy()
        self._profile_ui_state.clear()

        if not self._profiles:
            tk.Label(self._profiles_container,
                     text="No profiles yet. Add one below.",
                     bg=_BG, fg=_DIM,
                     font=("Segoe UI", 9)).pack(padx=8, pady=8, anchor="w")
            return

        # Render a card per profile. Active profile gets an ACCENT border.
        for pid, profile in self._profiles.items():
            self._render_profile_card(pid, profile, is_active=(pid == self._active_profile_id))

    def _render_profile_card(self, profile_id: str, profile: dict, is_active: bool):
        border_color = _ACC if is_active else _DIM
        card_outer = tk.Frame(self._profiles_container, bg=border_color)
        card_outer.pack(fill="x", pady=4)
        card = tk.Frame(card_outer, bg=_EBGD)
        card.pack(fill="x", padx=1, pady=1)

        # State
        state = {
            "expanded": False,
            "vars": {
                "label":    tk.StringVar(value=profile.get("label", profile_id)),
                "type":     tk.StringVar(value=profile.get("type", "openai_compatible")),
                "base_url": tk.StringVar(value=profile.get("base_url", "")),
                "model":    tk.StringVar(value=profile.get("model", "")),
                "api_key":  tk.StringVar(value=profile.get("api_key", "")),
            },
            "key_visible": False,
            "card": card,
            "card_outer": card_outer,
        }
        self._profile_ui_state[profile_id] = state

        # Header row (always visible)
        header = tk.Frame(card, bg=_EBGD, cursor="hand2")
        header.pack(fill="x", padx=10, pady=6)
        header.bind("<Button-1>", lambda e, pid=profile_id: self._toggle_profile_expand(pid))

        # Active indicator
        active_mark = "●" if is_active else "○"
        active_fg = _ACC if is_active else _DIM
        active_lbl = tk.Label(header, text=active_mark, bg=_EBGD, fg=active_fg,
                              font=("Segoe UI", 11), cursor="hand2")
        active_lbl.pack(side="left", padx=(0, 8))
        active_lbl.bind("<Button-1>", lambda e, pid=profile_id: self._set_active_profile(pid))

        # Label + type/model summary
        info = tk.Frame(header, bg=_EBGD, cursor="hand2")
        info.pack(side="left", fill="x", expand=True)
        info.bind("<Button-1>", lambda e, pid=profile_id: self._toggle_profile_expand(pid))

        tk.Label(info, text=profile.get("label", profile_id),
                 bg=_EBGD, fg=_FG, font=("Segoe UI", 10, "bold"),
                 cursor="hand2").pack(anchor="w")
        sub_text = profile.get("type", "?")
        if profile.get("model"):
            sub_text += f"  ·  {profile['model']}"
        if profile.get("base_url"):
            bu = profile["base_url"]
            sub_text += f"  ·  {bu[:48] + '…' if len(bu) > 48 else bu}"
        tk.Label(info, text=sub_text, bg=_EBGD, fg=_DIM,
                 font=("Segoe UI", 8), cursor="hand2").pack(anchor="w")

        # Action buttons (right side)
        actions = tk.Frame(header, bg=_EBGD)
        actions.pack(side="right")
        if not is_active:
            tk.Button(actions, text="Set active", bg=_EBGD, fg=_FG, bd=0,
                      font=("Segoe UI", 8), activebackground=_BG, cursor="hand2",
                      command=lambda pid=profile_id: self._set_active_profile(pid)
                      ).pack(side="left", padx=2)
        tk.Button(actions, text="Delete", bg=_EBGD, fg=_DANGER, bd=0,
                  font=("Segoe UI", 8), activebackground=_BG, cursor="hand2",
                  command=lambda pid=profile_id: self._delete_profile(pid)
                  ).pack(side="left", padx=2)

        # Body (hidden until expanded)
        body = tk.Frame(card, bg=_EBGD)
        state["body"] = body
        # Don't pack yet - _toggle_profile_expand handles it

    def _toggle_profile_expand(self, profile_id: str):
        state = self._profile_ui_state.get(profile_id)
        if not state:
            return
        state["expanded"] = not state["expanded"]
        body = state["body"]
        if state["expanded"]:
            self._render_profile_body(profile_id, body, state)
            body.pack(fill="x", padx=10, pady=(0, 8))
        else:
            for child in body.winfo_children():
                child.destroy()
            body.pack_forget()
        # Refresh scroll region
        self._body_canvas.update_idletasks()
        self._body_canvas.config(scrollregion=self._body_canvas.bbox("all"))

    def _render_profile_body(self, profile_id: str, body: tk.Frame, state: dict):
        v = state["vars"]
        # Name / label
        self._row_with_entry(body, "Name:", v["label"])

        # Type radio
        tr = tk.Frame(body, bg=_EBGD)
        tr.pack(fill="x", pady=2)
        tk.Label(tr, text="Type:", bg=_EBGD, fg=_FG, font=("Segoe UI", 9),
                 width=12, anchor="w").pack(side="left")
        for label, val in [("Local Ollama", "local_ollama"),
                           ("OpenAI-compatible", "openai_compatible")]:
            tk.Radiobutton(tr, text=label, variable=v["type"], value=val,
                           bg=_EBGD, fg=_FG, selectcolor=_BG,
                           activebackground=_EBGD, font=("Segoe UI", 9)
                           ).pack(side="left", padx=(0, 10))

        self._row_with_entry(body, "Base URL:", v["base_url"],
                             help_text="Required for OpenAI-compatible. Example: https://api.z.ai/v1")
        self._row_with_entry(body, "Model:", v["model"],
                             help_text="Model name as the provider expects it.")

        # API Key with Show/Hide
        api_row = tk.Frame(body, bg=_EBGD)
        api_row.pack(fill="x", pady=2)
        tk.Label(api_row, text="API Key:", bg=_EBGD, fg=_FG,
                 font=("Segoe UI", 9), width=12, anchor="w").pack(side="left")
        key_entry = tk.Entry(api_row, textvariable=v["api_key"],
                             bg=_BG, fg=_FG, insertbackground=_FG, bd=0,
                             font=("Consolas", 9),
                             show=("" if state["key_visible"] else "*"))
        key_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        state["key_entry"] = key_entry
        tk.Button(api_row, text=("Hide" if state["key_visible"] else "Show"),
                  bg=_BG, fg=_DIM, bd=0, font=("Segoe UI", 8),
                  activebackground=_EBGD, cursor="hand2",
                  command=lambda pid=profile_id: self._toggle_profile_key_visibility(pid)
                  ).pack(side="left")

        # Test button
        test_row = tk.Frame(body, bg=_EBGD)
        test_row.pack(fill="x", pady=(8, 2))
        tk.Button(test_row, text="Test connection", bg=_BG, fg=_FG, bd=0,
                  font=("Segoe UI", 9), activebackground=_EBGD,
                  cursor="hand2", padx=10, pady=3,
                  command=lambda pid=profile_id: self._test_profile(pid)
                  ).pack(side="left")
        # Test result gets its own full-width row so long error messages
        # (stack traces, 404 details, auth hints) wrap instead of truncating.
        state["test_label"] = tk.Label(body, text="", bg=_EBGD, fg=_DIM,
                                       font=("Segoe UI", 8),
                                       wraplength=580, justify="left",
                                       anchor="w")
        state["test_label"].pack(fill="x", pady=(4, 2))

    def _row_with_entry(self, parent, label, var, help_text=""):
        row = tk.Frame(parent, bg=_EBGD)
        row.pack(fill="x", pady=2)
        tk.Label(row, text=label, bg=_EBGD, fg=_FG,
                 font=("Segoe UI", 9), width=12, anchor="w").pack(side="left")
        tk.Entry(row, textvariable=var, bg=_BG, fg=_FG,
                 insertbackground=_FG, bd=0,
                 font=("Consolas", 9)).pack(side="left", fill="x", expand=True)
        if help_text:
            tk.Label(parent, text=help_text, bg=_EBGD, fg=_DIM,
                     font=("Segoe UI", 7), anchor="w"
                     ).pack(fill="x", padx=(72, 0), pady=(0, 4))

    def _toggle_profile_key_visibility(self, profile_id: str):
        state = self._profile_ui_state.get(profile_id)
        if not state or "key_entry" not in state:
            return
        state["key_visible"] = not state["key_visible"]
        state["key_entry"].config(show=("" if state["key_visible"] else "*"))
        # Re-render the body so the button text updates
        self._toggle_profile_expand(profile_id)   # collapse
        self._toggle_profile_expand(profile_id)   # re-expand

    # ── Profile actions ──────────────────────────────────────────────

    def _add_profile_from_preset(self):
        """Read the preset dropdown and add a new profile with those defaults."""
        self._sync_from_ui()   # keep any unsaved edits
        preset_label = self._preset_var.get()
        preset = next((p for p in self._provider_presets if p["label"] == preset_label),
                      self._provider_presets[0])
        # Generate a unique id based on preset
        base_id = preset["id"]
        new_id = base_id
        i = 2
        while new_id in self._profiles:
            new_id = f"{base_id}_{i}"
            i += 1
        self._profiles[new_id] = {
            "label":    preset["label"],
            "type":     preset["type"],
            "base_url": preset.get("base_url", ""),
            "model":    preset.get("model", ""),
            "api_key":  "",
        }
        # If this is the only profile, make it active
        if len(self._profiles) == 1:
            self._active_profile_id = new_id
        self._render_profile_list()
        # Auto-expand the new profile so user can fill in API key
        self._toggle_profile_expand(new_id)
        self._settings_status.config(
            text=f"Added {preset['label']!r}. Fill in the API key (if needed) and Save.",
            fg=_ACC)

    def _delete_profile(self, profile_id: str):
        if profile_id not in self._profiles:
            return
        self._sync_from_ui()
        del self._profiles[profile_id]
        if self._active_profile_id == profile_id:
            self._active_profile_id = next(iter(self._profiles), "")
        self._render_profile_list()
        self._settings_status.config(text="Profile removed. Save to persist.", fg=_ACC)

    def _set_active_profile(self, profile_id: str):
        if profile_id not in self._profiles:
            return
        self._sync_from_ui()
        self._active_profile_id = profile_id
        self._render_profile_list()
        self._settings_status.config(text="Active profile changed. Save to persist.", fg=_ACC)

    def _sync_from_ui(self):
        """Pull any values currently in StringVars back into self._profiles
        before we re-render or save, so edits aren't lost."""
        for pid, state in self._profile_ui_state.items():
            if pid not in self._profiles:
                continue
            v = state["vars"]
            self._profiles[pid] = {
                "label":    v["label"].get().strip() or pid,
                "type":     v["type"].get(),
                "base_url": v["base_url"].get().strip(),
                "model":    v["model"].get().strip(),
                "api_key":  v["api_key"].get(),
            }

    # ── Save / test ──────────────────────────────────────────────────

    def _save_settings(self):
        """Write all profiles + active id to config.json atomically."""
        self._sync_from_ui()
        # Validate: openai_compatible with empty base_url is a footgun
        for pid, p in self._profiles.items():
            if p.get("type") == "openai_compatible" and not p.get("base_url"):
                self._settings_status.config(
                    text=f"'{p.get('label', pid)}' is OpenAI-compatible but has no Base URL. Refusing to save.",
                    fg=_DANGER)
                return
        if not self._profiles:
            self._settings_status.config(text="No profiles to save.", fg=_DANGER)
            return
        if not self._active_profile_id or self._active_profile_id not in self._profiles:
            self._active_profile_id = next(iter(self._profiles))
        updates = {
            "llm_profiles":       self._profiles,
            "llm_active_profile": self._active_profile_id,
        }
        try:
            self._settings_save_config(updates)
        except Exception as e:
            self._settings_status.config(text=f"Save failed: {e}", fg=_DANGER)
            return
        self._settings_status.config(text="Saved.", fg=_SUCCESS)
        self.root.after(3000, lambda: self._settings_status.config(text="", fg=_DIM))

    def _test_profile(self, profile_id: str):
        """Save the current edits, mark this profile active, ping the provider."""
        self._sync_from_ui()
        if profile_id not in self._profiles:
            return
        # Temporarily set this profile as active so llm_provider.test_connection
        # uses it, regardless of which one is saved as active.
        original_active = self._active_profile_id
        self._active_profile_id = profile_id
        try:
            self._settings_save_config({
                "llm_profiles":       self._profiles,
                "llm_active_profile": profile_id,
            })
        except Exception as e:
            state = self._profile_ui_state.get(profile_id, {})
            if "test_label" in state:
                state["test_label"].config(text=f"Save failed: {e}", fg=_DANGER)
            self._active_profile_id = original_active
            return

        state = self._profile_ui_state.get(profile_id, {})
        test_label = state.get("test_label")
        if test_label:
            test_label.config(text="Testing...", fg=_DIM)

        import threading
        def _run():
            try:
                from llm_provider import test_connection
                ok, msg = test_connection()
            except Exception as e:
                ok, msg = False, f"crashed: {e}"
            def _apply():
                if test_label:
                    test_label.config(text=msg,
                                      fg=(_SUCCESS if ok else _DANGER))
            self.root.after(0, _apply)
        threading.Thread(target=_run, daemon=True, name="llm-test").start()

    def _open_config_file(self):
        """Open config.json in the default text handler."""
        try:
            from config_io import CONFIG_PATH
            os.startfile(str(CONFIG_PATH))
        except Exception as e:
            self._settings_status.config(text=f"Could not open config: {e}", fg=_DANGER)

    # ── Tab switching ─────────────────────────────────────────────────────────

    def _switch_tab(self):
        tab = self._tab_var.get()
        self._hist_frame.pack_forget()
        self._dict_frame.pack_forget()
        self._pending_frame.pack_forget()
        self._settings_frame.pack_forget()
        if tab == "history":
            self._populate_history()
            self._hist_frame.pack(fill="both", expand=True, padx=12, pady=8)
        elif tab == "dict":
            self._populate_dict()
            self._dict_frame.pack(fill="both", expand=True, padx=12, pady=8)
        elif tab == "pending":
            self._populate_pending()
            self._pending_frame.pack(fill="both", expand=True, padx=12, pady=8)
        elif tab == "settings":
            self._populate_settings()
            self._settings_frame.pack(fill="both", expand=True, padx=12, pady=8)

    # ── File watcher ──────────────────────────────────────────────────────────

    def _poll_files(self):
        """Check if any data file changed on disk and refresh the active tab."""
        tab = self._tab_var.get()

        hm = _file_mtime(_HISTORY_PATH)
        if hm != self._hist_mtime:
            self._hist_mtime = hm
            self._history = _load_history()
            if tab == "history":
                self._populate_history()

        dm = _file_mtime(_DICT_PATH)
        if dm != self._dict_mtime:
            self._dict_mtime = dm
            self._dictionary = _load_dict()
            if tab == "dict":
                self._populate_dict()

        pm = _file_mtime(_PENDING_PATH)
        if pm != self._pending_mtime:
            self._pending_mtime = pm
            self._pending = _load_pending()
            if tab == "pending":
                self._populate_pending()

        # Poll again in 1.5 seconds
        self.root.after(1500, self._poll_files)

    # ── Close ─────────────────────────────────────────────────────────────────

    def _on_close(self):
        self.root.destroy()


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = HistoryDictWindow()
    app.root.mainloop()
