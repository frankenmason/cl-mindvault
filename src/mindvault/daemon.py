"""Cross-platform daemon for automatic MindVault updates.

Supports:
- macOS: launchd (LaunchAgents)
- Windows: Task Scheduler (schtasks)
- Linux: systemd user service
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

LABEL = "com.mindvault.watcher"
TASK_NAME = "MindVaultWatcher"


def _detect_os() -> str:
    """Detect OS: 'macos', 'windows', or 'linux'."""
    system = platform.system()
    if system == "Darwin":
        return "macos"
    elif system == "Windows":
        return "windows"
    elif system == "Linux":
        return "linux"
    else:
        return "linux"  # fallback


# ---------------------------------------------------------------------------
# macOS — launchd
# ---------------------------------------------------------------------------

_MACOS_PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"

_MACOS_PLIST = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" \
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>-m</string>
        <string>mindvault.daemon</string>
        <string>run</string>
        <string>{root}</string>
    </array>
    <key>StartInterval</key>
    <integer>{interval}</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log}</string>
    <key>StandardErrorPath</key>
    <string>{err}</string>
</dict>
</plist>
"""


def _macos_install(root: Path, interval: int, output_dir: Path) -> bool:
    plist = _MACOS_PLIST.format(
        label=LABEL,
        python=sys.executable,
        root=str(root),
        interval=interval,
        log=str(output_dir / "daemon.log"),
        err=str(output_dir / "daemon.err"),
    )
    _MACOS_PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    _MACOS_PLIST_PATH.write_text(plist, encoding="utf-8")
    try:
        subprocess.run(["launchctl", "load", str(_MACOS_PLIST_PATH)],
                        capture_output=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return _MACOS_PLIST_PATH.exists()


def _macos_uninstall() -> bool:
    if not _MACOS_PLIST_PATH.exists():
        return True
    try:
        subprocess.run(["launchctl", "unload", str(_MACOS_PLIST_PATH)],
                        capture_output=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    try:
        _MACOS_PLIST_PATH.unlink()
    except OSError:
        return False
    return not _MACOS_PLIST_PATH.exists()


def _macos_status() -> dict:
    status = {"installed": _MACOS_PLIST_PATH.exists(), "running": False,
              "config_path": str(_MACOS_PLIST_PATH)}
    if status["installed"]:
        try:
            r = subprocess.run(["launchctl", "list", LABEL],
                               capture_output=True, text=True, timeout=5)
            status["running"] = r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    return status


# ---------------------------------------------------------------------------
# Windows — Task Scheduler
# ---------------------------------------------------------------------------

def _win_task_exists() -> bool:
    try:
        r = subprocess.run(
            ["schtasks", "/Query", "/TN", TASK_NAME],
            capture_output=True, text=True, timeout=10,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _windows_install(root: Path, interval: int, output_dir: Path) -> bool:
    python = sys.executable
    log_path = output_dir / "daemon.log"

    # schtasks interval is in minutes (minimum 1)
    minutes = max(1, interval // 60)

    # Create a wrapper script that schtasks will execute
    wrapper = output_dir / "mindvault_daemon.bat"
    wrapper.write_text(
        f'@echo off\r\n'
        f'"{python}" -m mindvault.daemon run "{root}" >> "{log_path}" 2>&1\r\n',
        encoding="utf-8",
    )

    # Remove existing task if any
    if _win_task_exists():
        try:
            subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
                           capture_output=True, timeout=10)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    try:
        r = subprocess.run(
            [
                "schtasks", "/Create",
                "/TN", TASK_NAME,
                "/TR", str(wrapper),
                "/SC", "MINUTE",
                "/MO", str(minutes),
                "/F",  # force overwrite
            ],
            capture_output=True, text=True, timeout=15,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _windows_uninstall() -> bool:
    if not _win_task_exists():
        return True
    try:
        r = subprocess.run(
            ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
            capture_output=True, timeout=10,
        )
        # Clean up wrapper
        wrapper = Path.home() / ".mindvault" / "mindvault_daemon.bat"
        if wrapper.exists():
            wrapper.unlink()
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _windows_status() -> dict:
    installed = _win_task_exists()
    running = False
    if installed:
        try:
            r = subprocess.run(
                ["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "LIST"],
                capture_output=True, text=True, timeout=10,
            )
            running = "Running" in r.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    return {"installed": installed, "running": running}


# ---------------------------------------------------------------------------
# Linux — systemd user service
# ---------------------------------------------------------------------------

_SYSTEMD_DIR = Path.home() / ".config" / "systemd" / "user"
_SERVICE_NAME = "mindvault-watcher"
_SERVICE_PATH = _SYSTEMD_DIR / f"{_SERVICE_NAME}.service"
_TIMER_PATH = _SYSTEMD_DIR / f"{_SERVICE_NAME}.timer"

_SYSTEMD_SERVICE = """\
[Unit]
Description=MindVault Knowledge Base Auto-Update

[Service]
Type=oneshot
ExecStart={python} -m mindvault.daemon run {root}
StandardOutput=append:{log}
StandardError=append:{err}

[Install]
WantedBy=default.target
"""

_SYSTEMD_TIMER = """\
[Unit]
Description=MindVault periodic update timer

[Timer]
OnBootSec=60
OnUnitActiveSec={interval}s
Persistent=true

[Install]
WantedBy=timers.target
"""


def _linux_install(root: Path, interval: int, output_dir: Path) -> bool:
    _SYSTEMD_DIR.mkdir(parents=True, exist_ok=True)

    service = _SYSTEMD_SERVICE.format(
        python=sys.executable,
        root=str(root),
        log=str(output_dir / "daemon.log"),
        err=str(output_dir / "daemon.err"),
    )
    timer = _SYSTEMD_TIMER.format(interval=interval)

    _SERVICE_PATH.write_text(service, encoding="utf-8")
    _TIMER_PATH.write_text(timer, encoding="utf-8")

    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"],
                        capture_output=True, timeout=10)
        subprocess.run(["systemctl", "--user", "enable", "--now", f"{_SERVICE_NAME}.timer"],
                        capture_output=True, timeout=10)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # systemd not available — files created but not activated
        return _SERVICE_PATH.exists()


def _linux_uninstall() -> bool:
    try:
        subprocess.run(["systemctl", "--user", "disable", "--now", f"{_SERVICE_NAME}.timer"],
                        capture_output=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    for p in [_SERVICE_PATH, _TIMER_PATH]:
        if p.exists():
            try:
                p.unlink()
            except OSError:
                return False

    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"],
                        capture_output=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return not _SERVICE_PATH.exists()


def _linux_status() -> dict:
    installed = _TIMER_PATH.exists()
    running = False
    if installed:
        try:
            r = subprocess.run(
                ["systemctl", "--user", "is-active", f"{_SERVICE_NAME}.timer"],
                capture_output=True, text=True, timeout=5,
            )
            running = r.stdout.strip() == "active"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    return {"installed": installed, "running": running}


# ---------------------------------------------------------------------------
# Public API — auto-dispatches by OS
# ---------------------------------------------------------------------------

def install_daemon(root: Path, interval: int = 300) -> bool:
    """Install platform-appropriate daemon for periodic MindVault updates.

    Args:
        root: Root directory to watch for projects.
        interval: Seconds between runs (default 300 = 5 minutes).

    Returns:
        True if daemon was installed successfully.
    """
    root = Path(root).resolve()
    output_dir = Path.home() / ".mindvault"
    output_dir.mkdir(parents=True, exist_ok=True)

    os_type = _detect_os()
    if os_type == "macos":
        return _macos_install(root, interval, output_dir)
    elif os_type == "windows":
        return _windows_install(root, interval, output_dir)
    elif os_type == "linux":
        return _linux_install(root, interval, output_dir)
    return False


def uninstall_daemon() -> bool:
    """Remove the daemon for the current platform.

    Returns:
        True if successfully removed.
    """
    os_type = _detect_os()
    if os_type == "macos":
        return _macos_uninstall()
    elif os_type == "windows":
        return _windows_uninstall()
    elif os_type == "linux":
        return _linux_uninstall()
    return False


def daemon_status() -> dict:
    """Check daemon status for the current platform.

    Returns:
        Dict with keys: installed, running, os, last_log_line, mechanism.
    """
    os_type = _detect_os()

    mechanism_map = {
        "macos": "launchd",
        "windows": "Task Scheduler",
        "linux": "systemd",
    }

    if os_type == "macos":
        status = _macos_status()
    elif os_type == "windows":
        status = _windows_status()
    elif os_type == "linux":
        status = _linux_status()
    else:
        status = {"installed": False, "running": False}

    status["os"] = os_type
    status["mechanism"] = mechanism_map.get(os_type, "unknown")

    # Last log line (cross-platform)
    log_path = Path.home() / ".mindvault" / "daemon.log"
    status["last_log_line"] = ""
    if log_path.exists():
        try:
            content = log_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.strip().split("\n")
            if lines:
                status["last_log_line"] = lines[-1]
        except OSError:
            pass

    return status


# ---------------------------------------------------------------------------
# Entry point for daemon execution
# ---------------------------------------------------------------------------

def _run_daemon(root_str: str) -> None:
    """Entry point: run global incremental update."""
    from datetime import datetime, timezone
    from mindvault.global_ import run_global_incremental

    root = Path(root_str).resolve()
    output_dir = Path.home() / ".mindvault"

    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        result = run_global_incremental(root, output_dir)
        print(f"[{timestamp}] MindVault daemon: {result}")
    except Exception as e:
        print(f"[{timestamp}] MindVault daemon error: {e}")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "run":
        _run_daemon(sys.argv[2])
    else:
        print(f"Usage: python -m mindvault.daemon run <root_path>")
        sys.exit(1)
