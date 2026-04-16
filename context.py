"""Windows context detection for cait-whisper.

Provides helpers to detect:
- Which application has focus (active window)
- Whether text is selected in the focused field, and if so, what it is
- The text immediately preceding the cursor (for "continuation" context)

All functions degrade gracefully: if a Windows API or optional dependency
is unavailable, the helper returns an empty/None value rather than raising.
Callers can treat missing context as equivalent to an empty field.

Design rationale:
- Active window detection uses ctypes only (stdlib) so it always works.
- Selection / preceding-text use UI Automation via pywinauto when available.
- We avoid destructive fallbacks (Ctrl+C probes) here - the caller decides
  whether that trade-off is acceptable for their use case.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from typing import Optional
import logging

log = logging.getLogger("cait-whisper")

# ── Optional: pywinauto for UI Automation ─────────────────────────────────
try:
    from pywinauto import Desktop  # type: ignore
    from pywinauto.application import Application  # type: ignore
    _HAS_PYWINAUTO = True
except Exception:
    _HAS_PYWINAUTO = False


# ── Active window detection (ctypes, always available) ───────────────────

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


@dataclass
class ActiveWindow:
    """Snapshot of the currently focused window."""
    hwnd: int
    title: str
    process_name: str   # e.g. "notepad.exe", "chrome.exe", "Code.exe"


def get_active_window() -> Optional[ActiveWindow]:
    """Return info about the foreground window, or None on failure."""
    try:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return None

        # Window title
        length = _user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value

        # Process ID from the window
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        # Open process and query image name
        handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not handle:
            return ActiveWindow(hwnd=hwnd, title=title, process_name="")

        try:
            buf2 = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            ok = _kernel32.QueryFullProcessImageNameW(handle, 0, buf2, ctypes.byref(size))
            if not ok:
                return ActiveWindow(hwnd=hwnd, title=title, process_name="")
            # Strip to just the executable name (last path segment)
            full_path = buf2.value
            process_name = full_path.rsplit("\\", 1)[-1] if "\\" in full_path else full_path
        finally:
            _kernel32.CloseHandle(handle)

        return ActiveWindow(hwnd=hwnd, title=title, process_name=process_name)
    except Exception as e:
        log.debug(f"[Context] get_active_window failed: {e}")
        return None


# ── Selection / preceding text via UI Automation (pywinauto) ──────────────

@dataclass
class FieldContext:
    """Snapshot of the text-field state at the time of transcription."""
    selection: str          # text currently selected (empty if none)
    preceding: str          # text before cursor (up to N chars)
    has_selection: bool     # True when selection is non-empty


def get_field_context(max_preceding: int = 200) -> FieldContext:
    """Best-effort field context detection via UI Automation.

    Returns an empty context (has_selection=False, strings empty) if
    pywinauto is not installed or the focused control doesn't expose
    a text pattern. Never raises.
    """
    empty = FieldContext(selection="", preceding="", has_selection=False)
    if not _HAS_PYWINAUTO:
        return empty

    try:
        # Get the focused element through the UIA backend
        focused = Desktop(backend="uia").get_active()  # top-level focused window
        # Find the element with keyboard focus inside it
        el = focused.element_info  # root; we'll drill in
        try:
            focused_el = focused.descendants(control_type=None)  # type: ignore[arg-type]
        except Exception:
            focused_el = []

        # Walk visible descendants looking for keyboard focus
        target = None
        try:
            for candidate in focused.descendants():
                try:
                    if candidate.has_keyboard_focus():
                        target = candidate
                        break
                except Exception:
                    continue
        except Exception:
            target = None

        if target is None:
            return empty

        # Selection via get_selection() when available
        selection_text = ""
        try:
            sel = target.get_selection()  # type: ignore[attr-defined]
            if sel:
                # Some controls return a list of ranges/strings
                if isinstance(sel, (list, tuple)):
                    selection_text = "".join(str(x) for x in sel if x)
                else:
                    selection_text = str(sel)
        except Exception:
            selection_text = ""

        # Preceding text is harder; try texts() as a rough approximation
        preceding_text = ""
        try:
            texts = target.texts()  # type: ignore[attr-defined]
            if texts:
                joined = "\n".join(t for t in texts if t)
                preceding_text = joined[-max_preceding:]
        except Exception:
            preceding_text = ""

        return FieldContext(
            selection=selection_text,
            preceding=preceding_text,
            has_selection=bool(selection_text.strip()),
        )
    except Exception as e:
        log.debug(f"[Context] get_field_context failed: {e}")
        return empty


# ── Convenience: one-shot context snapshot ────────────────────────────────

@dataclass
class Context:
    """Everything a command classifier might want to know."""
    window: Optional[ActiveWindow]
    field: FieldContext


def capture_context() -> Context:
    """Capture active window + field context in one call. Never raises."""
    return Context(
        window=get_active_window(),
        field=get_field_context(),
    )


# ── Self-test when run directly ───────────────────────────────────────────
if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.DEBUG)
    ctx = capture_context()
    print(json.dumps({
        "window": {
            "title": ctx.window.title if ctx.window else None,
            "process_name": ctx.window.process_name if ctx.window else None,
        },
        "field": {
            "has_selection": ctx.field.has_selection,
            "selection_len": len(ctx.field.selection),
            "preceding_len": len(ctx.field.preceding),
        },
        "pywinauto_available": _HAS_PYWINAUTO,
    }, indent=2))
