"""Shared config + JSON I/O helpers for cait-whisper.

Both the main client process (client.py) and the productivity panel process
(history_window.py) need to read and write config.json safely. This module
gives them a single implementation: atomic writes, defensive reads, and
log-safe redaction of secret-like keys.

Designed to have ZERO dependencies on either main module so it can be
imported anywhere without circular-import concerns. In particular, llm_provider
imports this module to read its own config without touching client.py.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).parent / "config.json"

# Pattern of config-key names whose values must NOT appear in logs.
# Matches case-insensitively against the WHOLE key name.
_SECRET_KEY_PATTERN = re.compile(r"(api_?key|secret|token|password|bearer)", re.I)


def load_config() -> dict:
    """Read config.json and return its contents as a dict. Returns {} on
    any error (missing file, invalid JSON, permission issue). Never raises."""
    try:
        if not CONFIG_PATH.exists():
            return {}
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def atomic_write(path: Path, data: Any) -> None:
    """Write `data` (anything JSON-serializable) to `path` atomically via
    temp-file + rename. Raises on failure - callers decide what to do."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    tmp.replace(path)


def save_config(updates: dict) -> None:
    """Merge `updates` into config.json and write atomically. Existing keys
    not in `updates` are preserved. Raises on failure."""
    current = load_config()
    current.update(updates)
    atomic_write(CONFIG_PATH, current)


def redact_for_log(value: Any) -> Any:
    """Return a copy of `value` (which can be a dict, list, or scalar) with
    any secret-like keys replaced by '***'. Pass log records through this
    helper before printing to avoid leaking API keys.

    Examples:
        redact_for_log({"llm_api_key": "sk-abc"}) -> {"llm_api_key": "***"}
        redact_for_log({"foo": "bar"})            -> {"foo": "bar"}
    """
    if isinstance(value, dict):
        result = {}
        for k, v in value.items():
            if isinstance(k, str) and _SECRET_KEY_PATTERN.search(k):
                # Redact: show length to confirm a value was set, hide the value
                if isinstance(v, str) and v:
                    result[k] = f"*** (set, {len(v)} chars)"
                else:
                    result[k] = "*** (empty)"
            else:
                result[k] = redact_for_log(v)
        return result
    if isinstance(value, (list, tuple)):
        return type(value)(redact_for_log(v) for v in value)
    return value


# ── Self-test ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    test_cases = [
        ({"llm_api_key": "sk-secret-12345"}, "should redact"),
        ({"username": "marco"}, "should keep"),
        ({"nested": {"api_key": "abc"}}, "nested should redact"),
        ({"llm_provider": "openai_compatible", "llm_api_key": "key", "llm_model": "gpt-4"},
         "mixed should partially redact"),
    ]
    for cfg, label in test_cases:
        out = redact_for_log(cfg)
        print(f"{label}: {cfg} -> {out}")
    sys.exit(0)
