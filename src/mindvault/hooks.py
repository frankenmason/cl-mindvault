"""Claude Code hook generator + git hook installer."""

from __future__ import annotations

import json
from pathlib import Path

_GIT_HOOK_MARKER = "# MindVault auto-update"

# Bump this whenever the hook script gains a behavior change so old
# broken installs get auto-overwritten on the next `mindvault install`.
MINDVAULT_HOOK_VERSION = 2

_PROMPT_HOOK_SCRIPT = '''#!/bin/bash
# MindVault auto-context hook
# MINDVAULT_HOOK_VERSION=2
#
# Reads stdin JSON (Claude Code UserPromptSubmit spec) and injects
# `mindvault query` results into the user prompt as `<mindvault-context>`.
#
# Why version 2:
#   - v1 read `$CLAUDE_USER_PROMPT`, an env var that does not exist in
#     the Claude Code hook environment. The script exited silently on
#     every prompt and nothing was ever injected.
#   - v1 also used `timeout`, which is not shipped on macOS by default
#     (coreutils provides `gtimeout`). Pipe captures failed there too.
#   - v1 ran with `set -e` implicitly in some code paths, so any of the
#     above failures short-circuited the hook with no error message.
# v2 fixes all three.

# No `set -e` — any failure silently falls through so the user's prompt
# still reaches Claude. Context injection is best-effort.

# 1) Read stdin (Claude Code hook contract)
INPUT="$(cat 2>/dev/null || true)"
[ -z "$INPUT" ] && exit 0

# 2) Extract `prompt` field from the JSON payload. Falls back to treating
# the entire stdin as plain text for manual testing.
PROMPT=$(printf '%s' "$INPUT" | python3 -c '
import json, sys
raw = sys.stdin.read()
try:
    data = json.loads(raw)
    p = (
        data.get("prompt")
        or data.get("userInput")
        or data.get("message")
        or data.get("input")
        or ""
    )
    print(p)
except Exception:
    print(raw)
' 2>/dev/null)

# 3) Basic filters
[ ${#PROMPT} -lt 10 ] && exit 0
case "$PROMPT" in
    /*) exit 0 ;;
esac

# 4) Need mindvault and a search index
command -v mindvault >/dev/null 2>&1 || exit 0

QUERY_ARGS=""
if [ -f "$HOME/.mindvault/search_index.json" ]; then
    QUERY_ARGS="--global"
elif [ ! -f "mindvault-out/search_index.json" ]; then
    exit 0
fi

# 5) Pick whichever timeout wrapper exists. macOS does not ship `timeout`
# by default but `gtimeout` is available via `brew install coreutils`.
TIMEOUT_CMD=""
if command -v gtimeout >/dev/null 2>&1; then
    TIMEOUT_CMD="gtimeout 10"
elif command -v timeout >/dev/null 2>&1; then
    TIMEOUT_CMD="timeout 10"
fi

# 6) Run the query and head-limit the output so we never blow the hook
# budget. Failures are swallowed so the user's prompt still goes through.
RESULT=$($TIMEOUT_CMD mindvault query "$PROMPT" $QUERY_ARGS 2>/dev/null | head -60)

# 7) Emit wrapped context so downstream prompts can see it.
if [ -n "$RESULT" ]; then
    echo "<mindvault-context>"
    echo "$RESULT"
    echo "</mindvault-context>"
fi

exit 0
'''
_GIT_HOOK_CONTENT = """
# MindVault auto-update
mindvault_update() {
  if command -v mindvault &>/dev/null; then
    mindvault update --quiet &
  fi
}
mindvault_update
"""

DIRTY_FILENAME = ".mindvault_dirty.json"


def install_git_hook(repo_dir: Path) -> bool:
    """Install post-commit hook for auto-update.

    Args:
        repo_dir: Path to the git repository root.

    Returns:
        True if hook was installed successfully.
    """
    repo_dir = Path(repo_dir)
    git_dir = repo_dir / ".git"
    if not git_dir.exists():
        return False

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_file = hooks_dir / "post-commit"

    # Check if already installed
    if hook_file.exists():
        existing = hook_file.read_text(encoding="utf-8")
        if _GIT_HOOK_MARKER in existing:
            return True  # Already installed
        # Append to existing hook
        content = existing.rstrip("\n") + "\n" + _GIT_HOOK_CONTENT
    else:
        content = "#!/bin/sh\n" + _GIT_HOOK_CONTENT

    hook_file.write_text(content, encoding="utf-8")
    hook_file.chmod(0o755)
    return True


def install_prompt_hook() -> bool:
    """Install the UserPromptSubmit hook script and register in settings.json.

    This hook automatically runs mindvault query on every user prompt
    and injects results as context. Claude doesn't need to decide —
    the system forces it.

    Pre-0.4.2 installs wrote a broken v1 script that read a nonexistent
    env var and used `timeout` (missing on macOS). We detect old copies
    by checking for the MINDVAULT_HOOK_VERSION=2 marker and overwrite
    them in place. Otherwise identical content is a no-op write.

    Returns:
        True if installed successfully.
    """
    # 1. Write the hook script
    hooks_dir = Path.home() / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hooks_dir / "mindvault-hook.sh"

    # Auto-upgrade: overwrite any prior install that does not carry the
    # current version marker. This fixes users upgrading from 0.4.1 or
    # earlier who are still running the broken v1 script.
    needs_write = True
    if hook_path.exists():
        try:
            existing = hook_path.read_text(encoding="utf-8")
            if f"MINDVAULT_HOOK_VERSION={MINDVAULT_HOOK_VERSION}" in existing:
                needs_write = False  # already on current version
        except (OSError, UnicodeDecodeError):
            pass

    if needs_write:
        hook_path.write_text(_PROMPT_HOOK_SCRIPT, encoding="utf-8")
    hook_path.chmod(0o755)

    # 2. Register in settings.json
    settings_path = Path.home() / ".claude" / "settings.json"
    settings = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            settings = {}

    hooks = settings.setdefault("hooks", {})
    prompt_hooks = hooks.setdefault("UserPromptSubmit", [])

    # Check if already present
    already_installed = any(
        "mindvault-hook" in str(h.get("hooks", h.get("command", "")))
        for h in prompt_hooks
    )
    if not already_installed:
        prompt_hooks.append({
            "hooks": [{
                "type": "command",
                "command": str(hook_path),
            }]
        })

    settings_path.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return True


def check_prompt_hook() -> list[dict]:
    """Diagnose the UserPromptSubmit hook installation end-to-end.

    Returns a list of ``{name, ok, detail}`` dicts covering:
        1. Hook file exists on disk
        2. Hook carries the current MINDVAULT_HOOK_VERSION marker
        3. Hook is executable
        4. Hook is registered in Claude Code settings.json
        5. `mindvault` CLI is on PATH
        6. A global or local search index is present
        7. Feeding a sample JSON prompt to the hook produces non-empty
           wrapped output (`<mindvault-context>`). This is the check
           that would have caught the v1 silent-failure bug immediately.

    Used by ``mindvault doctor`` to give users an actionable diagnosis
    without needing to trace through shell scripts by hand.
    """
    import subprocess

    results: list[dict] = []

    def add(name: str, ok: bool, detail: str) -> None:
        results.append({"name": name, "ok": ok, "detail": detail})

    # 1. Hook file exists
    hook_path = Path.home() / ".claude" / "hooks" / "mindvault-hook.sh"
    if not hook_path.exists():
        add("hook file", False, f"missing: {hook_path}")
        return results
    add("hook file", True, str(hook_path))

    # 2. Version marker
    try:
        hook_content = hook_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        add("hook readable", False, f"cannot read: {e}")
        return results

    marker = f"MINDVAULT_HOOK_VERSION={MINDVAULT_HOOK_VERSION}"
    if marker in hook_content:
        add("hook version", True, f"v{MINDVAULT_HOOK_VERSION}")
    else:
        add(
            "hook version",
            False,
            f"outdated — run `mindvault install` to upgrade to v{MINDVAULT_HOOK_VERSION}",
        )

    # 3. Executable
    import os as _os
    if _os.access(hook_path, _os.X_OK):
        add("hook executable", True, "chmod +x")
    else:
        add("hook executable", False, "run `chmod +x ~/.claude/hooks/mindvault-hook.sh`")

    # 4. Registered in settings.json
    settings_path = Path.home() / ".claude" / "settings.json"
    registered = False
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            prompt_hooks = (
                settings.get("hooks", {}).get("UserPromptSubmit", [])
            )
            for entry in prompt_hooks:
                hooks_list = entry.get("hooks", [])
                for h in hooks_list:
                    if "mindvault-hook" in str(h.get("command", "")):
                        registered = True
                        break
        except (json.JSONDecodeError, OSError):
            pass
    add(
        "hook registered",
        registered,
        "UserPromptSubmit in settings.json" if registered
        else "missing — run `mindvault install`",
    )

    # 5. mindvault on PATH
    try:
        which = subprocess.run(
            ["which", "mindvault"], capture_output=True, text=True, timeout=5,
        )
        cli_ok = which.returncode == 0
        add(
            "mindvault CLI",
            cli_ok,
            which.stdout.strip() if cli_ok else "not found on PATH",
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        add("mindvault CLI", False, f"check failed: {e}")
        return results

    # 6. Search index present
    global_index = Path.home() / ".mindvault" / "search_index.json"
    local_index = Path("mindvault-out") / "search_index.json"
    if global_index.exists():
        add("search index", True, f"global: {global_index}")
    elif local_index.exists():
        add("search index", True, f"local: {local_index}")
    else:
        add(
            "search index",
            False,
            "no global or local index — run `mindvault global <root>` or `mindvault install`",
        )

    # 7. End-to-end smoke test: feed stdin JSON, expect <mindvault-context>
    sample = '{"sessionId":"doctor","prompt":"mindvault doctor smoke test query","cwd":"/tmp"}'
    try:
        proc = subprocess.run(
            ["bash", str(hook_path)],
            input=sample,
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = proc.stdout or ""
        if "<mindvault-context>" in out and len(out.strip()) > len("<mindvault-context></mindvault-context>"):
            add("end-to-end", True, f"{len(out)} bytes injected")
        else:
            add(
                "end-to-end",
                False,
                "hook ran but emitted no context — check index and mindvault query output",
            )
    except subprocess.TimeoutExpired:
        add("end-to-end", False, "hook timed out after 30s")
    except OSError as e:
        add("end-to-end", False, f"could not execute: {e}")

    return results


def install_claude_hooks(settings_path: Path = None) -> bool:
    """Add PostToolUse + Stop hooks to Claude Code settings.

    This is opt-in only — not called automatically by install.

    Args:
        settings_path: Path to Claude Code settings.json.

    Returns:
        True if hooks were added successfully.
    """
    if settings_path is None:
        settings_path = Path.home() / ".claude" / "settings.json"
    settings_path = Path(settings_path)

    # Load existing settings or create new
    settings = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            settings = {}

    hooks = settings.setdefault("hooks", {})

    # PostToolUse hook
    post_tool_hooks = hooks.setdefault("PostToolUse", [])
    mv_post_hook = {
        "matcher": "Write|Edit",
        "command": 'mindvault mark-dirty "$FILE_PATH"',
    }
    # Check if already present
    already_has_post = any(
        h.get("command", "").startswith("mindvault mark-dirty")
        for h in post_tool_hooks
    )
    if not already_has_post:
        post_tool_hooks.append(mv_post_hook)

    # Stop hook
    stop_hooks = hooks.setdefault("Stop", [])
    mv_stop_hook = {
        "command": "mindvault flush",
    }
    already_has_stop = any(
        h.get("command", "").startswith("mindvault flush")
        for h in stop_hooks
    )
    if not already_has_stop:
        stop_hooks.append(mv_stop_hook)

    # Write settings
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return True


def mark_dirty(file_path: Path, output_dir: Path) -> None:
    """Flag a file as needing re-extraction.

    Args:
        file_path: Path to the file that changed.
        output_dir: MindVault output directory.
    """
    file_path = Path(file_path)
    output_dir = Path(output_dir)
    dirty_file = output_dir / DIRTY_FILENAME

    dirty_set: list[str] = []
    if dirty_file.exists():
        try:
            dirty_set = json.loads(dirty_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            dirty_set = []

    file_str = str(file_path.resolve())
    if file_str not in dirty_set:
        dirty_set.append(file_str)

    output_dir.mkdir(parents=True, exist_ok=True)
    dirty_file.write_text(
        json.dumps(dirty_set, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def flush(output_dir: Path) -> dict:
    """Process all dirty files. Called at session end.

    Args:
        output_dir: MindVault output directory.

    Returns:
        Dict with stats: {changed, files_processed} or {changed: 0}.
    """
    output_dir = Path(output_dir)
    dirty_file = output_dir / DIRTY_FILENAME

    if not dirty_file.exists():
        return {"changed": 0}

    try:
        dirty_list = json.loads(dirty_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"changed": 0}

    if not dirty_list:
        return {"changed": 0}

    # Find source_dir from output_dir (go up one level if output_dir is mindvault-out)
    # Try to find source by checking parent
    source_dir = output_dir.parent
    if not (source_dir / "src").exists() and not any(source_dir.glob("*.py")):
        # Fallback: use output_dir parent
        source_dir = output_dir.parent

    from mindvault.pipeline import run_incremental
    result = run_incremental(source_dir, output_dir)

    # Clear dirty list
    dirty_file.write_text("[]", encoding="utf-8")

    result["files_processed"] = len(dirty_list)
    return result
