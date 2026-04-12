"""Regression tests for 0.4.2 auto-context hook fix.

The v1 hook script was silently broken for months:
  - read a nonexistent `$CLAUDE_USER_PROMPT` env var → empty string
  - used `timeout`, which does not exist on macOS
  - ran with implicit `set -e`, so any failure killed the hook silently

These tests lock the v2 fix so a regression could not sneak past the
`_PROMPT_HOOK_SCRIPT` template or the install path.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from mindvault.hooks import (
    MINDVAULT_HOOK_VERSION,
    _PROMPT_HOOK_SCRIPT,
    check_prompt_hook,
    install_prompt_hook,
)


class TestPromptHookScriptTemplate:
    def test_version_marker_present(self):
        assert (
            f"MINDVAULT_HOOK_VERSION={MINDVAULT_HOOK_VERSION}"
            in _PROMPT_HOOK_SCRIPT
        )
        assert MINDVAULT_HOOK_VERSION >= 2

    def test_reads_stdin_not_env_var(self):
        """v1 bug: relied on $CLAUDE_USER_PROMPT which does not exist.

        The header comment still references the old var (as a changelog
        note), so we only assert it's absent from non-comment lines.
        """
        offending = [
            line for line in _PROMPT_HOOK_SCRIPT.splitlines()
            if "$CLAUDE_USER_PROMPT" in line and not line.lstrip().startswith("#")
        ]
        assert offending == [], f"v1 env-var reference survived: {offending}"
        assert "cat" in _PROMPT_HOOK_SCRIPT
        assert "json.loads" in _PROMPT_HOOK_SCRIPT

    def test_has_gtimeout_fallback(self):
        """macOS does not ship `timeout` — must fall back to gtimeout."""
        assert "gtimeout" in _PROMPT_HOOK_SCRIPT

    def test_no_hard_set_e(self):
        """Implicit set -e caused silent short-circuits in v1 after early
        error branches. v2 relies on explicit `|| true` / early exits."""
        # allow `set -e` only inside a comment (we mention it in the header)
        for line in _PROMPT_HOOK_SCRIPT.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert "set -e" not in stripped, f"unexpected set -e: {line!r}"

    def test_emits_wrapped_context(self):
        assert "<mindvault-context>" in _PROMPT_HOOK_SCRIPT
        assert "</mindvault-context>" in _PROMPT_HOOK_SCRIPT

    def test_respects_prompt_length_guard(self):
        """Very short prompts are noise — hook should skip them."""
        assert "-lt 10" in _PROMPT_HOOK_SCRIPT

    def test_slash_commands_skipped(self):
        """Slash commands go straight to Claude Code, not the hook."""
        assert "/*)" in _PROMPT_HOOK_SCRIPT  # case pattern


class TestInstallPromptHook:
    def test_fresh_install_writes_v2_script(self, tmp_path, monkeypatch):
        """A clean machine should get the v2 script with the marker."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        assert install_prompt_hook() is True

        hook_path = fake_home / ".claude" / "hooks" / "mindvault-hook.sh"
        assert hook_path.exists()
        content = hook_path.read_text(encoding="utf-8")
        assert f"MINDVAULT_HOOK_VERSION={MINDVAULT_HOOK_VERSION}" in content
        # Only check non-comment lines (the header comment references v1)
        non_comment_offense = [
            l for l in content.splitlines()
            if "$CLAUDE_USER_PROMPT" in l and not l.lstrip().startswith("#")
        ]
        assert non_comment_offense == []
        # Executable bit
        assert os.access(hook_path, os.X_OK)

    def test_auto_upgrades_v1_script(self, tmp_path, monkeypatch):
        """Existing v1 installs get overwritten on next install."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        # Plant a v1-style script without the version marker
        hooks_dir = fake_home / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True)
        v1_path = hooks_dir / "mindvault-hook.sh"
        v1_path.write_text(
            '#!/bin/bash\n'
            '# broken v1 — relies on $CLAUDE_USER_PROMPT\n'
            'PROMPT="$CLAUDE_USER_PROMPT"\n'
            'timeout 5 echo "never runs on macOS"\n'
        )

        assert install_prompt_hook() is True

        upgraded = v1_path.read_text(encoding="utf-8")
        assert f"MINDVAULT_HOOK_VERSION={MINDVAULT_HOOK_VERSION}" in upgraded
        # Only check non-comment lines (header comment intentionally
        # references v1 as changelog context).
        non_comment_offense = [
            l for l in upgraded.splitlines()
            if "$CLAUDE_USER_PROMPT" in l and not l.lstrip().startswith("#")
        ]
        assert non_comment_offense == []

    def test_noop_when_already_v2(self, tmp_path, monkeypatch):
        """Running install twice should not re-touch an up-to-date file."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        install_prompt_hook()
        hook_path = fake_home / ".claude" / "hooks" / "mindvault-hook.sh"
        first_mtime = hook_path.stat().st_mtime
        first_content = hook_path.read_text(encoding="utf-8")

        install_prompt_hook()
        second_content = hook_path.read_text(encoding="utf-8")
        assert first_content == second_content  # identical content

    def test_registers_in_settings_json(self, tmp_path, monkeypatch):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        install_prompt_hook()

        settings_path = fake_home / ".claude" / "settings.json"
        assert settings_path.exists()
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        prompt_hooks = data.get("hooks", {}).get("UserPromptSubmit", [])
        # At least one entry references the hook path
        found = False
        for entry in prompt_hooks:
            for h in entry.get("hooks", []):
                if "mindvault-hook" in h.get("command", ""):
                    found = True
        assert found


class TestRunHookEndToEnd:
    """Exercise the shell script directly against tmp_path sandbox."""

    def test_empty_stdin_exits_clean(self, tmp_path):
        hook_path = tmp_path / "hook.sh"
        hook_path.write_text(_PROMPT_HOOK_SCRIPT)
        hook_path.chmod(0o755)

        proc = subprocess.run(
            ["bash", str(hook_path)],
            input="",
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert proc.returncode == 0
        assert proc.stdout == ""  # nothing to emit

    def test_short_prompt_skipped(self, tmp_path):
        hook_path = tmp_path / "hook.sh"
        hook_path.write_text(_PROMPT_HOOK_SCRIPT)
        hook_path.chmod(0o755)

        proc = subprocess.run(
            ["bash", str(hook_path)],
            input=json.dumps({"prompt": "hi"}),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert proc.returncode == 0
        assert "<mindvault-context>" not in proc.stdout

    def test_slash_command_skipped(self, tmp_path):
        hook_path = tmp_path / "hook.sh"
        hook_path.write_text(_PROMPT_HOOK_SCRIPT)
        hook_path.chmod(0o755)

        proc = subprocess.run(
            ["bash", str(hook_path)],
            input=json.dumps({"prompt": "/help show me help"}),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert proc.returncode == 0
        assert "<mindvault-context>" not in proc.stdout

    def test_no_index_exits_without_error(self, tmp_path, monkeypatch):
        """When neither global nor local index exists, hook must skip
        silently — it must never block the user's prompt."""
        hook_path = tmp_path / "hook.sh"
        hook_path.write_text(_PROMPT_HOOK_SCRIPT)
        hook_path.chmod(0o755)

        fake_home = tmp_path / "home"
        fake_home.mkdir()
        env = {
            **os.environ,
            "HOME": str(fake_home),
            "PATH": os.environ.get("PATH", ""),
        }
        isolated_cwd = tmp_path / "nowhere"
        isolated_cwd.mkdir()

        proc = subprocess.run(
            ["bash", str(hook_path)],
            input=json.dumps({"prompt": "some question long enough"}),
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
            cwd=str(isolated_cwd),
        )
        assert proc.returncode == 0
        assert "<mindvault-context>" not in proc.stdout


class TestCheckPromptHook:
    def test_returns_list_of_results(self, tmp_path, monkeypatch):
        """Smoke test the diagnostic: clean fake home should report
        missing hook file (without crashing)."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        results = check_prompt_hook()
        assert isinstance(results, list)
        assert len(results) >= 1
        # Each entry has the required shape
        for r in results:
            assert set(r.keys()) == {"name", "ok", "detail"}
        # First check fails because nothing is installed
        assert results[0]["name"] == "hook file"
        assert results[0]["ok"] is False

    def test_post_install_hook_file_check_passes(self, tmp_path, monkeypatch):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        install_prompt_hook()
        results = check_prompt_hook()
        checks = {r["name"]: r for r in results}
        assert checks["hook file"]["ok"] is True
        assert checks["hook version"]["ok"] is True
        assert checks["hook registered"]["ok"] is True
