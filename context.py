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


def _get_field_context_inner(max_preceding: int) -> FieldContext:
    """Inner worker: walks the focused window's UI tree looking for the
    element that has keyboard focus. We wrap this in a hard timeout in
    the public `get_field_context()` so a slow UI (Chrome with many tabs,
    complex Electron UIs) can never block the transcription pipeline."""
    empty = FieldContext(selection="", preceding="", has_selection=False)
    if not _HAS_PYWINAUTO:
        return empty

    try:
        # Get the top-level focused window first
        focused = Desktop(backend="uia").get_active()
    except Exception as e:
        log.debug(f"[Context] get_active failed: {e}")
        return empty

    # Walk its descendants looking for the element with keyboard focus.
    # This IS O(tree size) but the timeout wrapper caps total time at 250ms.
    target = None
    try:
        for candidate in focused.descendants():
            try:
                if candidate.has_keyboard_focus():
                    target = candidate
                    break
            except Exception:
                continue
    except Exception as e:
        log.debug(f"[Context] descendants walk failed: {e}")
        return empty

    if target is None:
        return empty

    # Selection via get_selection() when available
    selection_text = ""
    try:
        sel = target.get_selection()  # type: ignore[attr-defined]
        if sel:
            if isinstance(sel, (list, tuple)):
                selection_text = "".join(str(x) for x in sel if x)
            else:
                selection_text = str(sel)
    except Exception:
        selection_text = ""

    # Preceding text via texts() as a rough approximation
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


def get_field_context(max_preceding: int = 200, timeout: float = 0.25) -> FieldContext:
    """Best-effort field context detection via UI Automation.

    Runs the UIA query in a worker thread with a hard timeout so a slow
    app (Chrome with many tabs, complex Electron UI) can never block the
    transcription pipeline for more than `timeout` seconds.

    Returns an empty context on any failure, including timeout. Never raises.
    """
    empty = FieldContext(selection="", preceding="", has_selection=False)
    if not _HAS_PYWINAUTO:
        return empty

    result_box: list = [empty]

    def _worker():
        try:
            result_box[0] = _get_field_context_inner(max_preceding)
        except Exception as e:
            log.debug(f"[Context] worker failed: {e}")

    import threading
    t = threading.Thread(target=_worker, daemon=True, name="uia-field-context")
    t.start()
    t.join(timeout=timeout)
    if t.is_alive():
        log.debug(f"[Context] get_field_context timed out after {timeout}s")
        return empty
    return result_box[0]


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


# ── Screen-context capture (v2.3) ──────────────────────────────────────────
# OCR the region around the user's cursor so the LLM classifier can factor
# in "what the user is looking at" when deciding how to handle an utterance.
# RapidOCR is imported lazily so users who don't enable screen context never
# pay the install cost.

_ocr_engine = None           # cached RapidOCR instance (lazy-loaded)
_ocr_available: Optional[bool] = None  # tri-state: None = untried, True/False = result


def _get_ocr():
    """Return a cached RapidOCR engine, or None if the package isn't installed."""
    global _ocr_engine, _ocr_available
    if _ocr_available is False:
        return None
    if _ocr_engine is not None:
        return _ocr_engine
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore
        _ocr_engine = RapidOCR()
        _ocr_available = True
        log.info("[Context] RapidOCR loaded for screen-context capture")
        return _ocr_engine
    except Exception as e:
        log.warning(f"[Context] RapidOCR unavailable (install rapidocr-onnxruntime): {e}")
        _ocr_available = False
        return None


def get_cursor_pos() -> Optional[tuple[int, int]]:
    """Return the current cursor position as (x, y), or None on failure."""
    try:
        class _POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        pt = _POINT()
        if _user32.GetCursorPos(ctypes.byref(pt)):
            return (pt.x, pt.y)
    except Exception as e:
        log.debug(f"[Context] get_cursor_pos failed: {e}")
    return None


def capture_screen_region(center_x: int, center_y: int,
                          width: int = 700, height: int = 400):
    """Grab a PIL Image of a rectangle centered on (center_x, center_y).
    Clips to screen bounds. Returns None on failure."""
    try:
        from PIL import ImageGrab  # type: ignore
        left   = max(0, center_x - width // 2)
        top    = max(0, center_y - height // 2)
        right  = left + width
        bottom = top + height
        return ImageGrab.grab(bbox=(left, top, right, bottom))
    except Exception as e:
        log.debug(f"[Context] capture_screen_region failed: {e}")
        return None


def ocr_image(pil_image) -> str:
    """Run OCR on a PIL image and return the extracted text. Empty string
    on failure (package missing, image invalid, etc.)."""
    if pil_image is None:
        return ""
    engine = _get_ocr()
    if engine is None:
        return ""
    try:
        import numpy as np  # type: ignore
        arr = np.array(pil_image)
        result, _ = engine(arr)
        if not result:
            return ""
        lines = [item[1] for item in result if item and len(item) > 1]
        return "\n".join(lines)
    except Exception as e:
        log.warning(f"[Context] ocr_image failed: {e}")
        return ""


def capture_screen_context(max_chars: int = 2000) -> str:
    """One-shot: cursor -> screen region -> OCR text. Returns "" on failure
    (including when RapidOCR isn't installed)."""
    pos = get_cursor_pos()
    if pos is None:
        return ""
    image = capture_screen_region(pos[0], pos[1])
    if image is None:
        return ""
    text = ocr_image(image).strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "…"
    return text


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
