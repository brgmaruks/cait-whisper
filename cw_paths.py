"""Filesystem path resolution that behaves correctly whether cait-whisper
runs from source (`python client.py`) or as a frozen PyInstaller bundle.

Two distinct kinds of path:

  app_dir()       WRITABLE user-data directory: config.json, the log,
                  history.json, dictionary.json, pending_corrections.json,
                  and the generated assets/cait.ico.
                  - From source: the repo directory (unchanged from the old
                    `Path(__file__).parent` behaviour).
                  - Frozen: the folder that contains the .exe, i.e. wherever
                    the user unzipped the download. That folder is user-
                    writable and keeps a user's data next to the app.

  resource_path() READ-ONLY bundled resource: config.example.json, assets/.
                  - From source: the repo directory.
                  - Frozen: PyInstaller's extraction dir (sys._MEIPASS).

Named cw_paths (not plain `paths`) to avoid any collision with third-party
modules once everything is bundled together by PyInstaller.
"""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    """True when running inside a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Writable directory for user data (config, logs, history, dictionary)."""
    if is_frozen():
        # The bundled exe lives in the unzipped folder; write alongside it.
        return Path(sys.executable).resolve().parent
    # Source: next to the .py files, exactly as before.
    return Path(__file__).resolve().parent


def resource_path(name: str = "") -> Path:
    """Path to a read-only resource bundled with the app (config.example.json,
    assets/, etc.). Frozen builds extract these under sys._MEIPASS; from source
    they sit next to the .py files."""
    base = getattr(sys, "_MEIPASS", None)
    root = Path(base) if base else Path(__file__).resolve().parent
    return (root / name) if name else root
