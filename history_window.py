"""
cait-whisper  ·  History & Dictionary window
Standalone process — fully decoupled from the main transcription widget.
Reads / writes history.json, dictionary.json, and pending_corrections.json
in the same directory.  Auto-refreshes when the files change on disk.
"""

import json
import os
import sys
import time
import tkinter as tk
from pathlib import Path

try:
    import pyperclip
except ImportError:
    pyperclip = None

# ─── Paths ────────────────────────────────────────────────────────────────────
_DIR          = Path(__file__).parent
_HISTORY_PATH = _DIR / "history.json"
_DICT_PATH    = _DIR / "dictionary.json"
_PENDING_PATH = _DIR / "pending_corrections.json"
_MAX_HISTORY  = 50

# ─── Theme ────────────────────────────────────────────────────────────────────
_BG   = "#18120E"
_FG   = "#D4C4B0"
_ACC  = "#C87941"
_DIM  = "#5A4030"
_EBGD = "#221810"

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
        self.root.title("cait-whisper")
        self.root.resizable(True, True)
        self.root.geometry("460x560")
        self.root.configure(bg=_BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

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
        # Title bar
        bar = tk.Frame(self.root, bg=_BG)
        bar.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(bar, text="cait-whisper", bg=_BG, fg=_ACC,
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Button(bar, text="\u2715", bg=_BG, fg=_DIM, bd=0,
                  font=("Segoe UI", 10), activebackground=_BG,
                  command=self._on_close).pack(side="right")

        # Tab buttons — three tabs
        self._tab_var = tk.StringVar(value="history")
        tab_bar = tk.Frame(self.root, bg=_BG)
        tab_bar.pack(fill="x", padx=12)
        for label, key in [("Recent transcriptions", "history"),
                            ("Dictionary",            "dict"),
                            ("Pending",               "pending")]:
            tk.Radiobutton(
                tab_bar, text=label, variable=self._tab_var, value=key,
                bg=_BG, fg=_FG, selectcolor=_EBGD,
                activebackground=_BG, font=("Segoe UI", 9),
                indicatoron=False, padx=10, pady=4, bd=0, relief="flat",
                command=self._switch_tab,
            ).pack(side="left", padx=(0, 4))

        tk.Frame(self.root, bg=_DIM, height=1).pack(fill="x", padx=12, pady=(4, 0))

        self._build_history_tab()
        self._build_dict_tab()
        self._build_pending_tab()
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

        # Search box (left side)
        tk.Label(tb, text="🔍", bg=_BG, fg=_DIM,
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._populate_history())
        search_entry = tk.Entry(
            tb, textvariable=self._search_var,
            bg=_EBGD, fg=_FG, insertbackground=_FG,
            font=("Segoe UI", 9), width=20, bd=0, relief="flat",
        )
        search_entry.pack(side="left", ipady=3)

        # Clear-search button (shown when search has text)
        def _clear_search():
            self._search_var.set("")
            search_entry.focus_set()
        tk.Button(tb, text="✕", bg=_BG, fg=_DIM, bd=0,
                  font=("Segoe UI", 8), activebackground=_BG,
                  cursor="hand2", command=_clear_search,
                  ).pack(side="left", padx=(2, 8))

        # Clear-all button (right side)
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

            # Delete button
            del_btn = tk.Button(
                t, text="\u2715", bg=bg, fg=_DIM, bd=0,
                font=("Segoe UI", 7), activebackground=bg, cursor="hand2",
                command=(lambda idx=orig_idx: self._delete_history_item(idx)),
            )
            t.window_create("end", window=del_btn, padx=4, pady=2)
            self._embedded_widgets.append(del_btn)

            # Copy button
            if pyperclip:
                cp_btn = tk.Button(
                    t, text="\u2398", bg=bg, fg=_ACC, bd=0,
                    font=("Segoe UI", 10), activebackground=bg, cursor="hand2",
                    command=(lambda tx=text: pyperclip.copy(tx)),
                )
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
        tk.Label(add_row, text="\u2192  Replace with:", bg=_BG, fg=_FG,
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

            btn = tk.Button(
                t, text="\u2715", bg=bg, fg=_DIM, bd=0,
                font=("Segoe UI", 8), activebackground=bg, cursor="hand2",
                command=(lambda key=k: self._del_dict_entry(key)),
            )
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
            del_btn = tk.Button(
                t, text="\u2715", bg=bg, fg=_DIM, bd=0,
                font=("Segoe UI", 7), activebackground=bg, cursor="hand2",
                command=(lambda k=key: self._discard_pending(k)),
            )
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

    # ── Tab switching ─────────────────────────────────────────────────────────

    def _switch_tab(self):
        tab = self._tab_var.get()
        self._hist_frame.pack_forget()
        self._dict_frame.pack_forget()
        self._pending_frame.pack_forget()
        if tab == "history":
            self._populate_history()
            self._hist_frame.pack(fill="both", expand=True, padx=12, pady=8)
        elif tab == "dict":
            self._populate_dict()
            self._dict_frame.pack(fill="both", expand=True, padx=12, pady=8)
        else:
            self._populate_pending()
            self._pending_frame.pack(fill="both", expand=True, padx=12, pady=8)

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
