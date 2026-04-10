"""User settings management — ~/.mindvault/config.json."""

from __future__ import annotations

import json
from pathlib import Path

_CONFIG_DIR = Path.home() / ".mindvault"
_CONFIG_FILE = _CONFIG_DIR / "config.json"

_DEFAULTS = {
    "llm_endpoint": None,
    "auto_approve_api": False,
    "max_tokens_per_file": 4000,
    "preferred_provider": None,
}


def load_config() -> dict:
    """Load config from ~/.mindvault/config.json, merging with defaults."""
    if _CONFIG_FILE.exists():
        try:
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            merged = {**_DEFAULTS, **user_cfg}
            return merged
        except (json.JSONDecodeError, OSError):
            pass
    return dict(_DEFAULTS)


def save_config(config: dict) -> None:
    """Save config to ~/.mindvault/config.json."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get(key: str, default=None):
    """Get a single config value."""
    cfg = load_config()
    return cfg.get(key, default)


def set(key: str, value) -> None:
    """Set a single config value and persist."""
    cfg = load_config()
    cfg[key] = value
    save_config(cfg)
