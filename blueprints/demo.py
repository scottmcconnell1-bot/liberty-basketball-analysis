"""
Demo-mode uninstall API for the LibertyDemo Windows package.

Enabled when DEMO_MODE=1 (or a flag file exists). The web DONE button
POSTs here to schedule a TEMP cleanup handoff and stop the Flask process.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading
from pathlib import Path

from flask import Blueprint, after_this_request, jsonify

demo_bp = Blueprint("demo", __name__)

# Overridable in tests (avoid hard-killing the pytest process).
_exit_delay_sec = 0.5


def demo_mode_enabled() -> bool:
    """True when running under the LibertyDemo installer session."""
    env = (os.environ.get("DEMO_MODE") or "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    temp_flag = Path(tempfile.gettempdir()) / "LibertyDemo_mode.flag"
    if temp_flag.is_file():
        return True
    local_flag = Path.cwd() / ".liberty_demo_mode"
    return local_flag.is_file()


def _persist_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA") or ""
    if local:
        return Path(local) / "LibertyBasketballDemo"
    return Path.home() / "AppData" / "Local" / "LibertyBasketballDemo"


def _write_cleanup_handoff() -> Path:
    """Write a TEMP .bat that wipes the demo install after this process exits."""
    persist = str(_persist_dir())
    temp = tempfile.gettempdir()
    bat_path = Path(temp) / "LibertyDemo_web_cleanup.bat"
    # Delay so Flask can finish the HTTP response and exit before we delete files.
    content = f"""@echo off
setlocal EnableExtensions
title Liberty Demo Cleanup
echo Liberty Demo web DONE — waiting for server exit...
timeout /t 3 /nobreak >nul

set "PERSIST_DIR={persist}"
set "SHORTCUT_NAME=Liberty Basketball Demo"

echo Removing leftover Desktop shortcuts...
for %%D in ("%USERPROFILE%\\Desktop" "%USERPROFILE%\\OneDrive\\Desktop" "%PUBLIC%\\Desktop") do (
  if exist "%%~D\\%SHORTCUT_NAME%.url" del /f /q "%%~D\\%SHORTCUT_NAME%.url" 2>nul
  if exist "%%~D\\%SHORTCUT_NAME%.lnk" del /f /q "%%~D\\%SHORTCUT_NAME%.lnk" 2>nul
)

echo Removing session install...
if exist "%PERSIST_DIR%" (
  rd /s /q "%PERSIST_DIR%" 2>nul
  if exist "%PERSIST_DIR%" (
    timeout /t 2 /nobreak >nul
    rd /s /q "%PERSIST_DIR%" 2>nul
  )
)

echo Removing TEMP LibertyDemo leftovers...
del /f /q "%TEMP%\\LibertyDemo_*.log" 2>nul
del /f /q "%TEMP%\\LibertyDemo_*.log.err" 2>nul
del /f /q "%TEMP%\\LibertyDemo_*.log.server" 2>nul
del /f /q "%TEMP%\\LibertyDemo_mode.flag" 2>nul
del /f /q "%TEMP%\\LibertyDemo_done.flag" 2>nul
for /d %%D in ("%TEMP%\\LibertyDemo_*") do rd /s /q "%%~fD" 2>nul

echo Demo cleanup finished.
timeout /t 2 /nobreak >nul
del /f /q "%~f0" 2>nul
exit /b 0
"""
    bat_path.write_text(content, encoding="ascii", errors="replace")
    return bat_path


def _spawn_cleanup_bat() -> Path | None:
    """Write done flag + start cleanup bat (must happen before process exit)."""
    done_flag = Path(tempfile.gettempdir()) / "LibertyDemo_done.flag"
    try:
        done_flag.write_text("1\n", encoding="ascii")
    except OSError:
        pass

    bat = _write_cleanup_handoff()
    creationflags = 0
    if os.name == "nt":
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        creationflags = 0x00000008 | 0x00000200
    try:
        subprocess.Popen(
            ["cmd.exe", "/c", str(bat)],
            cwd=tempfile.gettempdir(),
            creationflags=creationflags,
            close_fds=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
    except OSError:
        # Still stop the server; the outer install_and_run.bat will clean up.
        return None
    return bat


def _schedule_hard_exit(delay_sec: float | None = None) -> None:
    """Exit after delay so the HTTP response can flush to the client first."""
    wait = _exit_delay_sec if delay_sec is None else delay_sec

    def _hard_exit() -> None:
        os._exit(0)

    threading.Timer(wait, _hard_exit).start()


@demo_bp.route("/api/demo/done", methods=["POST"])
@demo_bp.route("/api/demo/uninstall", methods=["POST"])
def demo_done():
    """Schedule uninstall cleanup and stop the Flask server.

    Critical ordering: spawn cleanup bat, return JSON 200, THEN exit after a
    short delay. Exiting before the response is sent makes fetch() fail and
    shows "Could not reach the demo uninstall API".
    """
    if not demo_mode_enabled():
        return jsonify({"ok": False, "error": "Demo mode is not active."}), 403

    _spawn_cleanup_bat()

    @after_this_request
    def _exit_after_response(response):
        # Timer starts after Flask has prepared the response for send.
        _schedule_hard_exit(0.5)
        return response

    return jsonify(
        {
            "ok": True,
            "message": "Demo uninstalling. You can close this browser tab.",
        }
    )


@demo_bp.route("/api/demo/status", methods=["GET"])
def demo_status():
    """Lightweight probe used by smoke tests / UI."""
    return jsonify({"ok": True, "demo_mode": demo_mode_enabled()})
