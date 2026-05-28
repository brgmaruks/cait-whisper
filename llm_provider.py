"""LLM provider abstraction for cait-whisper.

Single dispatch point for every LLM call. Routes to either local Ollama
or any OpenAI-compatible HTTP endpoint based on config. Returns None on
any failure so callers can preserve graceful-degradation semantics.

Providers supported:
- local_ollama       (default; uses `ollama` package; localhost:11434)
- openai_compatible  (uses `openai` package with user-supplied base_url;
                     covers Z.AI, Groq, Together, OpenAI, DeepSeek,
                     self-hosted vLLM, Tailscale Ollama-over-HTTPS, etc.)

This module deliberately does NOT import client.py or commands.py to avoid
circular-import traps. It reads its own config via config_io.load_config().
"""

from __future__ import annotations

import logging
from typing import Optional

from config_io import load_config

log = logging.getLogger("cait-whisper")

# Default model for local Ollama if neither llm_model nor ollama_model is set.
_DEFAULT_LOCAL_MODEL = "llama3.2:3b"


def _get_provider_config() -> dict:
    """Read the current provider config. Returns a dict with normalized
    keys: provider, base_url, api_key, model. Supports three config layouts:

    1. New v2.5.0 profiles: `llm_profiles` dict + `llm_active_profile` id
    2. Interim flat keys: `llm_provider`, `llm_base_url`, `llm_api_key`, `llm_model`
    3. v2.4 legacy: only `ollama_model` set

    Fallbacks cascade down cleanly so any config file works."""
    cfg = load_config()

    # (1) Profile-based layout
    profiles = cfg.get("llm_profiles")
    active_id = cfg.get("llm_active_profile")
    if isinstance(profiles, dict) and active_id and active_id in profiles:
        p = profiles[active_id]
        return {
            "provider": p.get("type", "local_ollama"),
            "base_url": p.get("base_url", ""),
            "api_key":  p.get("api_key", ""),
            "model":    p.get("model") or _DEFAULT_LOCAL_MODEL,
        }

    # (2) Flat-key fallback (v2.5.0-beta)
    if "llm_provider" in cfg:
        return {
            "provider": cfg.get("llm_provider", "local_ollama"),
            "base_url": cfg.get("llm_base_url", ""),
            "api_key":  cfg.get("llm_api_key", ""),
            "model":    cfg.get("llm_model") or cfg.get("ollama_model") or _DEFAULT_LOCAL_MODEL,
        }

    # (3) v2.4 legacy: default to local Ollama using ollama_model
    return {
        "provider": "local_ollama",
        "base_url": "",
        "api_key":  "",
        "model":    cfg.get("ollama_model", _DEFAULT_LOCAL_MODEL),
    }


# ── Presets for well-known providers ──────────────────────────────────────
# Used by the Settings tab's "Add profile" dropdown so users can skip the
# copy-paste dance of looking up each provider's base URL.

PROVIDER_PRESETS = [
    {
        "id": "local_ollama",
        "label": "Local Ollama",
        "type": "local_ollama",
        "base_url": "",
        "model": "llama3.2:3b",
        "hint": "Runs on your machine at localhost:11434. No API key needed.",
    },
    {
        "id": "zai",
        "label": "Z.AI",
        "type": "openai_compatible",
        "base_url": "https://api.z.ai/v1",
        "model": "glm-4-flash",
        "hint": "Zhipu GLM models. Fast and inexpensive.",
    },
    {
        "id": "groq",
        "label": "Groq",
        "type": "openai_compatible",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "hint": "Very fast Llama / Mixtral inference. Generous free tier.",
    },
    {
        "id": "openai",
        "label": "OpenAI",
        "type": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "hint": "GPT-4o-mini recommended for cost; gpt-4o for quality.",
    },
    {
        "id": "together",
        "label": "Together AI",
        "type": "openai_compatible",
        "base_url": "https://api.together.xyz/v1",
        "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "hint": "Wide model catalog. Pay per token.",
    },
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "type": "openai_compatible",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "hint": "Inexpensive Chinese models, strong at code.",
    },
    {
        "id": "custom",
        "label": "Custom (self-hosted, Tailscale, etc.)",
        "type": "openai_compatible",
        "base_url": "",
        "model": "",
        "hint": "For self-hosted vLLM, Tailscale Ollama, or any OpenAI-compatible endpoint.",
    },
]


def _build_messages(prompt: str, system_prompt: Optional[str]) -> list[dict]:
    """Compose a chat-completions messages list. When a system prompt is
    provided, the model follows its instructions far more reliably than when
    everything is shoved into the user message."""
    msgs = []
    if system_prompt:
        msgs.append({"role": "system", "content": system_prompt})
    msgs.append({"role": "user", "content": prompt})
    return msgs


def _llm_call_ollama(
    prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
    system_prompt: Optional[str] = None,
) -> Optional[str]:
    """Local Ollama backend. Identical to v2.4 behavior."""
    try:
        import ollama  # type: ignore
    except Exception as e:
        log.warning(f"[LLM:local_ollama] ollama package unavailable: {e}")
        return None
    try:
        # Note: the ollama package uses its own internal timeout based on the
        # underlying httpx client; we can't easily inject a per-call timeout.
        # For local connections this is rarely an issue.
        resp = ollama.chat(
            model=model,
            messages=_build_messages(prompt, system_prompt),
            options={"temperature": temperature, "num_predict": max_tokens},
        )
        return resp["message"]["content"].strip()
    except Exception as e:
        log.warning(f"[LLM:local_ollama] call failed: {e}")
        return None


def _llm_call_openai(
    prompt: str,
    model: str,
    base_url: str,
    api_key: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
    json_mode: bool,
    system_prompt: Optional[str] = None,
) -> Optional[str]:
    """OpenAI-compatible backend. Works with Z.AI, Groq, Together, OpenAI,
    DeepSeek, self-hosted vLLM, Tailscale-Ollama-over-HTTPS, etc."""
    if not base_url:
        log.warning(
            "[LLM:openai_compatible] llm_base_url is empty. Refusing to silently "
            "fall back to api.openai.com - that would violate the local-first promise. "
            "Set llm_base_url in config.json or Settings tab."
        )
        return None
    try:
        from openai import OpenAI  # type: ignore
    except Exception as e:
        log.warning(f"[LLM:openai_compatible] openai package unavailable: {e}")
        return None

    try:
        client = OpenAI(
            base_url=base_url,
            api_key=api_key or "no-key",   # some local servers ignore the key
            timeout=timeout,
        )
        kwargs = {
            "model": model,
            "messages": _build_messages(prompt, system_prompt),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            # Many providers respect this; ones that don't will ignore it.
            kwargs["response_format"] = {"type": "json_object"}
        resp = client.chat.completions.create(**kwargs)
        content = resp.choices[0].message.content
        return content.strip() if content else None
    except Exception as e:
        log.warning(f"[LLM:openai_compatible] call failed: {e}")
        return None


def llm_call(
    prompt: str,
    *,
    temperature: float = 0.3,
    max_tokens: int = 512,
    model: Optional[str] = None,
    timeout: float = 30.0,
    json_mode: bool = False,
    system_prompt: Optional[str] = None,
) -> Optional[str]:
    """Single dispatch point for LLM calls. Returns the text response, or
    None on any failure (network, missing package, bad config, etc.).

    Parameters:
      prompt:        the user message (content to act on)
      temperature:   sampling temperature (0.0..1.0)
      max_tokens:    maximum response length
      model:         optional override for the configured model name
      timeout:       network timeout in seconds (matters for remote)
      json_mode:     if True, ask provider to return strict JSON (used by
                     command classifier; supported by most modern providers,
                     silently ignored by ones that don't)
      system_prompt: optional behavior/format instructions sent as the
                     system role. Separating system from user reliably
                     improves instruction-following vs. cramming everything
                     into a single user message (v2.5.1 best practice).
    """
    pcfg = _get_provider_config()
    chosen_model = model or pcfg["model"]
    provider = pcfg["provider"]
    log.debug(f"[LLM] dispatching to {provider} (model={chosen_model}, json={json_mode}, "
              f"sys={bool(system_prompt)})")

    if provider == "local_ollama":
        return _llm_call_ollama(prompt, chosen_model, temperature, max_tokens, timeout,
                                system_prompt=system_prompt)
    if provider == "openai_compatible":
        return _llm_call_openai(
            prompt,
            chosen_model,
            pcfg["base_url"],
            pcfg["api_key"],
            temperature,
            max_tokens,
            timeout,
            json_mode,
            system_prompt=system_prompt,
        )
    log.warning(f"[LLM] unknown provider {provider!r}; falling back to local_ollama")
    return _llm_call_ollama(prompt, chosen_model, temperature, max_tokens, timeout,
                            system_prompt=system_prompt)


def get_active_provider_name() -> str:
    """Return the human-readable name of the active provider for status displays."""
    pcfg = _get_provider_config()
    return {
        "local_ollama": "Local Ollama",
        "openai_compatible": "OpenAI-compatible",
    }.get(pcfg["provider"], pcfg["provider"])


def test_connection() -> tuple[bool, str]:
    """Send a tiny prompt to the active provider and report the outcome.
    Used by the Settings tab "Test connection" button. Returns (ok, message).

    Unlike llm_call (which swallows exceptions and returns None so the caller
    can degrade gracefully), this helper catches the exception and returns
    its message verbatim so users can see exactly what's wrong."""
    pcfg = _get_provider_config()
    prompt = "Say OK."

    if pcfg["provider"] == "local_ollama":
        try:
            import ollama  # type: ignore
        except Exception as e:
            return False, f"Local Ollama not importable: {e}"
        try:
            resp = ollama.chat(
                model=pcfg["model"],
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.0, "num_predict": 10},
            )
            out = resp["message"]["content"].strip()
            return True, f"OK. Model: {pcfg['model']}. Reply: {out[:80]!r}"
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    # openai_compatible
    if not pcfg["base_url"]:
        return False, "Base URL is empty. Refusing to call - would silently hit api.openai.com."
    try:
        from openai import OpenAI  # type: ignore
    except Exception as e:
        return False, f"openai package not importable: {e}"
    try:
        client = OpenAI(
            base_url=pcfg["base_url"],
            api_key=pcfg["api_key"] or "no-key",
            timeout=15.0,
        )
        resp = client.chat.completions.create(
            model=pcfg["model"],
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=10,
        )
        out = (resp.choices[0].message.content or "").strip()
        return True, f"OK. Model: {pcfg['model']}. Reply: {out[:80]!r}"
    except Exception as e:
        # Surface the full error. Provider endpoints return structured errors
        # (401 bad key, 404 wrong path, 400 bad model name, etc.) which are
        # way more diagnostic than a generic "no response".
        msg = str(e)
        if len(msg) > 400:
            msg = msg[:400] + "..."
        return False, f"{type(e).__name__}: {msg}"


# ── Self-test ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    pcfg = _get_provider_config()
    print(f"Active provider: {get_active_provider_name()}")
    print(f"Resolved config: {pcfg}")
    print()
    print("Sending test prompt...")
    ok, msg = test_connection()
    print(f"Result: ok={ok}  msg={msg}")
