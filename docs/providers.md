# LLM Providers

cait-whisper sends prompts to a local LLM (default: Ollama) for three things:

- **Voice command classification** when the regex fast-path doesn't match (COMMAND mode)
- **Selection rewriting** ("make this more formal", "shorten this", etc.)
- **LLM Cleanup** post-processing (optional toggle)

As of v2.5.0, you can route those calls to any **OpenAI-compatible HTTP endpoint** instead of running Ollama locally. This unlocks:

- **Z.AI** (Zhipu GLM models)
- **Groq** (very fast Llama / Mixtral inference)
- **Together AI**
- **OpenAI** (GPT-4, GPT-4o-mini, etc.)
- **DeepSeek**
- **Self-hosted vLLM** behind your firewall
- **A remote Ollama** over Tailscale or any HTTPS endpoint
- **Anything else** that exposes the OpenAI chat completions API

Local Ollama remains the default for privacy. No data leaves your machine unless you change the provider.

## How to switch

### Option A: Settings tab (recommended)

cait-whisper lets you save **multiple provider profiles** (Z.AI for fast rewrites, Groq for latency, your Tailscale Ollama for privacy, OpenAI for quality, etc.). One is marked ACTIVE at a time. Switching is a single click - you don't lose your other profiles' API keys.

1. Right-click the widget -> "History & Dictionary"
2. Click the **Settings** tab
3. Use the **"Add from preset"** dropdown + button to create a new profile from a known provider (Z.AI, Groq, OpenAI, Together, DeepSeek, Custom). The Base URL and default model are pre-filled.
4. Click the new profile's row to expand its fields. Enter your API key. Click **Show** to verify you typed the key correctly.
5. Click **Test connection** to ping the provider with a short prompt. Green "OK" = works.
6. Click the hollow circle on the left side of the card (or the "Set active" button) to mark this profile ACTIVE.
7. Click **Save** at the top right.

The next LLM call (next voice command, next LLM cleanup, etc.) uses the active profile.

To switch active providers later: open Settings, click another profile's circle, Save. No re-typing keys.

### Option B: Edit `config.json` directly

```json
{
  "llm_active_profile": "zai_fast",
  "llm_profiles": {
    "local_ollama": {
      "label": "Local Ollama",
      "type": "local_ollama",
      "model": "llama3.2:3b"
    },
    "zai_fast": {
      "label": "Z.AI fast",
      "type": "openai_compatible",
      "base_url": "https://api.z.ai/v1",
      "model": "glm-4-flash",
      "api_key": "..."
    },
    "groq_llama": {
      "label": "Groq Llama 70B",
      "type": "openai_compatible",
      "base_url": "https://api.groq.com/openai/v1",
      "model": "llama-3.3-70b-versatile",
      "api_key": "..."
    }
  }
}
```

Restart not required - cait-whisper picks up the change on the next LLM call.

**Backward compatibility**: v2.4 and early v2.5.0 configs that used the flat `llm_provider` / `llm_base_url` / etc. keys are still read on first load. The Settings tab migrates them into profiles the first time you save.

## Provider examples

### Z.AI (GLM models)

```json
{
  "llm_provider": "openai_compatible",
  "llm_base_url": "https://api.z.ai/v1",
  "llm_api_key": "...",
  "llm_model": "glm-4-flash"
}
```

### Groq (fast inference)

```json
{
  "llm_provider": "openai_compatible",
  "llm_base_url": "https://api.groq.com/openai/v1",
  "llm_api_key": "...",
  "llm_model": "llama-3.3-70b-versatile"
}
```

### OpenAI

```json
{
  "llm_provider": "openai_compatible",
  "llm_base_url": "https://api.openai.com/v1",
  "llm_api_key": "...",
  "llm_model": "gpt-4o-mini"
}
```

### Self-hosted Ollama over Tailscale (or any HTTPS reverse proxy)

```json
{
  "llm_provider": "openai_compatible",
  "llm_base_url": "https://ollama.example.ts.net/v1",
  "llm_api_key": "ignored",
  "llm_model": "llama3.2:3b"
}
```

Most reverse-proxied Ollama setups expose the OpenAI-compat endpoint at `/v1`. Tailscale users can typically use `https://<hostname>.ts.net/v1` if their server runs Ollama with the OpenAI-compat shim enabled.

### Local Ollama (default)

```json
{
  "llm_provider": "local_ollama",
  "ollama_model": "llama3.2:3b"
}
```

No URL or key needed. cait-whisper talks to `localhost:11434`.

## Privacy & security

- **Privacy**: when `llm_provider` is `openai_compatible`, prompts are sent to whatever URL you configured. Make sure you trust that endpoint. The local-Ollama default sends nothing off your machine.
- **API keys** are stored in `config.json` in plaintext. Anyone with read access to your home directory can see them. cait-whisper itself requires Administrator on Windows, so the threat model already assumes admin-level trust on the machine.
- **Logs are redacted**: cait-whisper's log file (`cait-whisper.log`) replaces secret-like config keys with `***` so an API key that's saved through Settings or `_save_config_keys` does NOT appear in plaintext in the log. Verify with: search for `llm_api_key` in `cait-whisper.log` after saving - you should see `*** (set, N chars)`, not the key itself.
- **No silent fallback**: if you set `llm_provider` to `openai_compatible` but leave the Base URL empty, cait-whisper refuses to call the provider rather than silently falling back to `api.openai.com`. This protects users who never intended to talk to OpenAI from accidentally doing so.

## Troubleshooting

**"Test connection" returns "No response"**
- Check that the Base URL includes the version path (usually `/v1`)
- Confirm the API key is valid
- Verify the model name exactly matches what the provider exposes
- Check `cait-whisper.log` for the actual error

**"openai package unavailable"**
- The `openai` Python package is installed by `setup.bat`. If you skipped it, run `pip install openai` in the venv.

**"Refusing to silently fall back to api.openai.com"**
- You picked `openai_compatible` but didn't set a Base URL. Either set one, or switch back to `local_ollama`.

**Slow responses after switching to remote**
- Some providers (like Z.AI) have variable latency depending on region and load. Try Groq for fastest inference or pick a smaller model.

**Local Ollama no longer auto-starts when LLM Cleanup is enabled**
- This is correct. If `llm_provider` is `openai_compatible`, cait-whisper does NOT auto-start the local Ollama subprocess (it would just sit idle). To re-enable local-Ollama-with-auto-start, switch `llm_provider` back to `local_ollama`.

## Going back to local-only

Set `llm_provider` to `local_ollama` (or just delete the `llm_provider` key from `config.json` - the default is local). cait-whisper will resume using your local Ollama instance.
