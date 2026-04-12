"""LLM auto-detection and calling — urllib only, no requests dependency."""

from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error
from typing import Optional


def detect_llm() -> dict:
    """Auto-detect available LLM provider.

    Priority:
    1. config.llm_endpoint (user override)
    2. localhost:8080 (Gemma MLX)
    3. Ollama (config.ollama_host → $OLLAMA_HOST → localhost:11434)
    4. ANTHROPIC_API_KEY env var
    5. OPENAI_API_KEY env var
    6. None

    Honors `config.llm_model` as a final override for any detected provider.

    Returns:
        Dict with keys: provider, endpoint, model, is_local, api_key.
    """
    from mindvault.config import get as cfg_get

    result = _detect_llm_raw()
    # Final override: only applied to local providers (gemma, ollama, custom
    # OpenAI-compatible endpoints). Remote API providers (anthropic, openai)
    # have their own model namespaces — forcing e.g. `gemma3:e4b` on OpenAI
    # would just error at call time. Use provider-specific env vars or config
    # for remote APIs.
    model_override = cfg_get("llm_model")
    if (
        model_override
        and result.get("provider")
        and result.get("is_local")
    ):
        result = dict(result)
        result["model"] = model_override
    return result


def _detect_llm_raw() -> dict:
    """Inner detection. See detect_llm for priority order."""
    from mindvault.config import get as cfg_get

    empty = {"provider": None, "endpoint": None, "model": None, "is_local": False, "api_key": None}

    # 1. User-configured endpoint
    user_endpoint = cfg_get("llm_endpoint")
    if user_endpoint:
        return {
            "provider": "custom",
            "endpoint": user_endpoint,
            "model": "custom",
            "is_local": True,
            "api_key": None,
        }

    preferred = cfg_get("preferred_provider")

    # 2. Gemma MLX at localhost:8080
    if preferred in (None, "gemma"):
        gemma_model = _detect_gemma_model("http://localhost:8080")
        if gemma_model:
            return {
                "provider": "gemma",
                "endpoint": "http://localhost:8080",
                "model": gemma_model,
                "is_local": True,
                "api_key": None,
            }

    # 3. Ollama — honor config.ollama_host, then $OLLAMA_HOST, then localhost
    if preferred in (None, "ollama"):
        ollama_host = (
            cfg_get("ollama_host")
            or os.environ.get("OLLAMA_HOST")
            or "http://localhost:11434"
        )
        if not ollama_host.startswith(("http://", "https://")):
            ollama_host = f"http://{ollama_host}"
        if _ping_local(ollama_host):
            return {
                "provider": "ollama",
                "endpoint": ollama_host,
                "model": _detect_ollama_model(ollama_host),
                "is_local": True,
                "api_key": None,
            }

    # 4. Anthropic API key
    if preferred in (None, "anthropic"):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            return {
                "provider": "anthropic",
                "endpoint": "https://api.anthropic.com",
                "model": "claude-haiku-4-5-20251001",
                "is_local": False,
                "api_key": api_key,
            }

    # 5. OpenAI API key
    if preferred in (None, "openai"):
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            return {
                "provider": "openai",
                "endpoint": "https://api.openai.com",
                "model": "gpt-4o-mini",
                "is_local": False,
                "api_key": api_key,
            }

    return empty


def _detect_gemma_model(base_url: str) -> str | None:
    """Detect available Gemma model at a local endpoint. Returns model ID or None."""
    try:
        req = urllib.request.Request(f"{base_url}/v1/models", method="GET")
        resp = urllib.request.urlopen(req, timeout=2)
        data = json.loads(resp.read().decode("utf-8"))
        models = data.get("data", [])
        # Prefer gemma model
        for m in models:
            mid = m.get("id", "")
            if "gemma" in mid.lower():
                return mid
        # Fallback to first model
        if models:
            return models[0]["id"]
    except Exception:
        pass
    return None


def _detect_ollama_model(base_url: str) -> str:
    """Detect best available Ollama model, preferring gemma3, gemma, qwen3, qwen.

    Queries Ollama's `/api/tags` endpoint to list installed models.
    Falls back to 'llama3' if nothing is found.
    """
    try:
        req = urllib.request.Request(f"{base_url}/api/tags", method="GET")
        resp = urllib.request.urlopen(req, timeout=2)
        data = json.loads(resp.read().decode("utf-8"))
        models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        if not models:
            return "llama3"
        # Prefer recent small local models in order
        for pref in ("gemma3", "gemma", "qwen3", "qwen", "llama3"):
            for m in models:
                if pref in m.lower():
                    return m
        return models[0]
    except Exception:
        return "llama3"


def _ping_local(base_url: str) -> bool:
    """Ping a local LLM server with 2-second timeout."""
    try:
        # Try /v1/models first (OpenAI-compatible)
        req = urllib.request.Request(f"{base_url}/v1/models", method="GET")
        urllib.request.urlopen(req, timeout=2)
        return True
    except Exception:
        pass
    try:
        # Try /api/tags (Ollama)
        req = urllib.request.Request(f"{base_url}/api/tags", method="GET")
        urllib.request.urlopen(req, timeout=2)
        return True
    except Exception:
        pass
    return False


def call_llm(prompt: str, text: str, provider: dict = None) -> str:
    """Call LLM with prompt + text content.

    Args:
        prompt: System/instruction prompt.
        text: Content text to analyze.
        provider: Provider dict from detect_llm(). If None, auto-detect.

    Returns:
        LLM response text, or empty string on failure.
    """
    if provider is None:
        provider = detect_llm()

    if provider["provider"] is None:
        return ""

    full_prompt = f"{prompt}\n\n---\n\n{text}"

    try:
        if provider["provider"] == "anthropic":
            return _call_anthropic(full_prompt, provider)
        elif provider["provider"] == "openai":
            return _call_openai(full_prompt, provider)
        else:
            # Local (gemma, ollama, custom) — OpenAI-compatible
            return _call_openai_compatible(full_prompt, provider)
    except Exception as e:
        print(f"LLM call failed: {e}", file=sys.stderr)
        return ""


def _call_openai_compatible(prompt: str, provider: dict) -> str:
    """Call OpenAI-compatible local API (Gemma, Ollama, custom)."""
    endpoint = provider['endpoint'].rstrip('/')
    if endpoint.endswith('/v1'):
        endpoint = endpoint[:-3]
    url = f"{endpoint}/v1/chat/completions"
    from mindvault.config import get as cfg_get
    is_local = provider.get("is_local", True)
    max_tokens = cfg_get("llm_max_tokens", 16000 if is_local else 4000)
    timeout = cfg_get("llm_timeout", 300 if is_local else 60)

    body = json.dumps({
        "model": provider["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": max_tokens,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=timeout)
    data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def _call_anthropic(prompt: str, provider: dict) -> str:
    """Call Anthropic Messages API."""
    url = "https://api.anthropic.com/v1/messages"
    body = json.dumps({
        "model": provider["model"],
        "max_tokens": 4000,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": provider["api_key"],
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=60)
    data = json.loads(resp.read().decode("utf-8"))
    return data["content"][0]["text"]


def _call_openai(prompt: str, provider: dict) -> str:
    """Call OpenAI Chat Completions API."""
    url = "https://api.openai.com/v1/chat/completions"
    body = json.dumps({
        "model": provider["model"],
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {provider['api_key']}",
        },
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=60)
    data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def estimate_cost(text: str, provider: dict) -> float:
    """Estimate API cost for processing text.

    Uses len(text)/4 as token approximation.
    Haiku: input $0.80/M, output $4.00/M
    GPT-4o-mini: input $0.15/M, output $0.60/M
    Local: $0.00

    Returns:
        Estimated cost in USD.
    """
    if provider.get("is_local", False):
        return 0.0

    input_tokens = len(text) / 4
    # Assume output is ~1/4 of input for extraction
    output_tokens = input_tokens / 4

    p = provider.get("provider", "")
    if p == "anthropic":
        cost = (input_tokens * 0.80 / 1_000_000) + (output_tokens * 4.00 / 1_000_000)
    elif p == "openai":
        cost = (input_tokens * 0.15 / 1_000_000) + (output_tokens * 0.60 / 1_000_000)
    else:
        cost = 0.0

    return round(cost, 6)


def confirm_api_usage(provider: dict, cost: float) -> bool:
    """Ask user for consent before API call (non-local LLM).

    If auto_approve_api is true in config, returns True immediately.
    If not running interactively (no tty), returns False unless auto_approve.

    Returns:
        True if user approves, False otherwise.
    """
    from mindvault.config import get as cfg_get

    if cfg_get("auto_approve_api", False):
        return True

    # Check if we're in an interactive terminal
    if not sys.stdin.isatty():
        return False

    p_name = provider.get("provider", "unknown").capitalize()
    model = provider.get("model", "unknown")
    print(f"\n\u26a0\ufe0f  No local LLM detected. Using {p_name} {model} (API key found).")
    print(f"    Estimated cost for this file: ~${cost:.4f}")

    try:
        answer = input("    Continue? [y/N]: ").strip().lower()
        return answer in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False
