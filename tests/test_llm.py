"""Unit tests for mindvault.llm provider detection and config overrides.

Locks the 0.2.9 / 0.3.1 behavior: ollama_host / OLLAMA_HOST resolution,
dynamic model detection fallback, and the llm_model override being
local-only (remote API providers must keep their own model namespace).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from mindvault import llm


class TestDetectOllamaModel:
    def test_unreachable_host_falls_back_to_llama3(self):
        assert llm._detect_ollama_model("http://10.255.255.254:11434") == "llama3"

    def test_wrong_endpoint_shape_falls_back(self):
        # Gemma MLX on 8080 returns /v1/models but not /api/tags → fallback
        # (Only meaningful if you actually have something listening on 8080;
        # if nothing is there, still falls back.)
        assert llm._detect_ollama_model("http://localhost:65530") == "llama3"

    def test_prefers_gemma3_when_available(self):
        class FakeResp:
            def __init__(self, payload):
                import json
                self._body = json.dumps(payload).encode()
            def read(self):
                return self._body

        fake_payload = {
            "models": [
                {"name": "llama3:8b"},
                {"name": "gemma3:e4b"},
                {"name": "qwen3:4b"},
            ]
        }

        def fake_urlopen(req, timeout=2):
            return FakeResp(fake_payload)

        with patch.object(llm.urllib.request, "urlopen", side_effect=fake_urlopen):
            model = llm._detect_ollama_model("http://fake:11434")
            assert model == "gemma3:e4b"

    def test_falls_through_to_first_model_when_no_preference_matches(self):
        class FakeResp:
            def __init__(self, payload):
                import json
                self._body = json.dumps(payload).encode()
            def read(self):
                return self._body

        fake_payload = {"models": [{"name": "mistral:7b"}, {"name": "phi:3b"}]}

        with patch.object(
            llm.urllib.request,
            "urlopen",
            side_effect=lambda req, timeout=2: FakeResp(fake_payload),
        ):
            model = llm._detect_ollama_model("http://fake:11434")
            assert model == "mistral:7b"


class TestLlmModelOverride:
    """llm_model config override must NOT leak into remote API providers."""

    def test_override_applies_to_local(self):
        """Simulate a local provider being detected and verify override applies."""
        with patch.object(
            llm,
            "_detect_llm_raw",
            return_value={
                "provider": "ollama",
                "endpoint": "http://localhost:11434",
                "model": "llama3",
                "is_local": True,
                "api_key": None,
            },
        ):
            with patch.object(
                llm,
                "cfg_get" if hasattr(llm, "cfg_get") else "_noop",
                create=True,
            ):
                # Use a lambda to capture cfg_get calls
                def cfg_stub(key, default=None):
                    return "gemma3:e4b" if key == "llm_model" else None

                with patch("mindvault.config.get", side_effect=cfg_stub):
                    result = llm.detect_llm()
                    assert result["provider"] == "ollama"
                    assert result["model"] == "gemma3:e4b"  # override applied

    def test_override_skipped_for_remote_provider(self):
        """The critical test: remote providers must keep their own model."""
        with patch.object(
            llm,
            "_detect_llm_raw",
            return_value={
                "provider": "anthropic",
                "endpoint": "https://api.anthropic.com",
                "model": "claude-haiku-4-5-20251001",
                "is_local": False,
                "api_key": "sk-ant-...",
            },
        ):
            def cfg_stub(key, default=None):
                return "gemma3:e4b" if key == "llm_model" else None

            with patch("mindvault.config.get", side_effect=cfg_stub):
                result = llm.detect_llm()
                assert result["provider"] == "anthropic"
                # CRITICAL: override must NOT leak into remote API provider
                assert result["model"] == "claude-haiku-4-5-20251001"
                assert result["model"] != "gemma3:e4b"

    def test_override_skipped_for_openai(self):
        with patch.object(
            llm,
            "_detect_llm_raw",
            return_value={
                "provider": "openai",
                "endpoint": "https://api.openai.com",
                "model": "gpt-4o-mini",
                "is_local": False,
                "api_key": "sk-...",
            },
        ):
            def cfg_stub(key, default=None):
                return "qwen3:4b" if key == "llm_model" else None

            with patch("mindvault.config.get", side_effect=cfg_stub):
                result = llm.detect_llm()
                assert result["model"] == "gpt-4o-mini"

    def test_no_override_leaves_model_alone(self):
        """When llm_model is unset, the provider's own model must pass through."""
        with patch.object(
            llm,
            "_detect_llm_raw",
            return_value={
                "provider": "ollama",
                "endpoint": "http://localhost:11434",
                "model": "llama3",
                "is_local": True,
                "api_key": None,
            },
        ):
            def cfg_stub(key, default=None):
                return None

            with patch("mindvault.config.get", side_effect=cfg_stub):
                result = llm.detect_llm()
                assert result["model"] == "llama3"
