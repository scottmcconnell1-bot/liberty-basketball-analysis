#!/usr/bin/env python3
"""
One-click local launcher for Liberty Basketball Analysis.

Checks prerequisites, installs Python deps into .venv, initializes the DB,
starts the Flask app, and opens the dashboard in your browser.

Usage:
  python scripts/launch_liberty.py
  python scripts/launch_liberty.py --port 8081 --no-browser

Windows: double-click ``Start Liberty.bat`` in the repo root.
Linux:   bash scripts/launch_liberty.sh
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
MIN_PYTHON = (3, 12)
MAX_PYTHON = (3, 13)
DEFAULT_PORT = 8080
WAIT_SECONDS = 90


def _log(message: str) -> None:
    print(f"[liberty] {message}", flush=True)


def _warn(message: str) -> None:
    print(f"[liberty] WARNING: {message}", flush=True)


def _venv_python() -> Path:
    scripts_dir = "Scripts" if os.name == "nt" else "bin"
    name = "python.exe" if os.name == "nt" else "python"
    return ROOT / ".venv" / scripts_dir / name


def _python_ok(version: tuple[int, int, int]) -> bool:
    return MIN_PYTHON <= version[:2] <= MAX_PYTHON


def _find_system_python() -> list[str]:
    # Prefer the interpreter running this script: on Linux a uv/pyenv-managed
    # 3.12/3.13 is often NOT on PATH under the name python3.12/python3.13.
    candidates: list[list[str]] = [[sys.executable]]
    if os.name == "nt":
        candidates.extend([
            ["py", "-3.12"],
            ["py", "-3.13"],
            ["python"],
            ["python3"],
        ])
    else:
        candidates.extend([
            ["python3.12"],
            ["python3.13"],
            ["python3"],
            ["python"],
        ])
    for cmd in candidates:
        if shutil.which(cmd[0]) is None:
            continue
        try:
            result = subprocess.run(
                cmd + ["-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                continue
            parts = tuple(int(p) for p in result.stdout.strip().split("."))
            if _python_ok(parts):
                return cmd
        except (OSError, ValueError):
            continue
    return []


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    _log("$ " + " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, check=check)


def _try_winget_install(package_id: str, label: str) -> bool:
    if os.name != "nt" or shutil.which("winget") is None:
        return False
    _log(f"Attempting to install {label} with winget ({package_id})...")
    result = subprocess.run(
        [
            "winget", "install", "-e", "--id", package_id,
            "--accept-package-agreements", "--accept-source-agreements",
        ],
        cwd=ROOT,
        check=False,
    )
    return result.returncode == 0


def ensure_python() -> list[str]:
    cmd = _find_system_python()
    if cmd:
        _log(f"Using Python: {' '.join(cmd)}")
        return cmd

    if os.name == "nt":
        for package_id, label in (
            ("Python.Python.3.12", "Python 3.12"),
            ("Python.Python.3.13", "Python 3.13"),
        ):
            if _try_winget_install(package_id, label):
                cmd = _find_system_python()
                if cmd:
                    _log(f"Python installed. Using: {' '.join(cmd)}")
                    return cmd

    raise RuntimeError(
        "Python 3.12 or 3.13 is required. Install from https://www.python.org/downloads/ "
        "or run: winget install Python.Python.3.12"
    )


def ensure_ffmpeg() -> None:
    if shutil.which("ffmpeg"):
        _log("ffmpeg found.")
        return

    _warn("ffmpeg not found. Film upload/analysis may fail until ffmpeg is installed.")
    if os.name == "nt":
        if _try_winget_install("Gyan.FFmpeg", "ffmpeg"):
            if shutil.which("ffmpeg"):
                _log("ffmpeg installed.")
                return
        _warn("Install manually: winget install Gyan.FFmpeg")
    else:
        _warn("Install manually: sudo apt install ffmpeg  (Debian/Ubuntu)")


def ensure_git() -> None:
    if shutil.which("git"):
        return
    _warn("git not found. You can still run the app from an extracted copy of the repo.")


def ensure_venv(python_cmd: list[str]) -> Path:
    venv_python = _venv_python()
    if venv_python.exists():
        _log("Virtual environment already exists.")
        return venv_python

    _log("Creating virtual environment (.venv)...")
    _run(python_cmd + ["-m", "venv", str(ROOT / ".venv")])
    if not venv_python.exists():
        raise RuntimeError(f"Failed to create venv at {venv_python}")
    return venv_python


def ensure_dependencies(venv_python: Path) -> None:
    marker = ROOT / ".venv" / ".liberty_deps_installed"
    if marker.exists():
        _log("Python dependencies already installed (marker present).")
        return

    _log("Installing Python dependencies (first run may take a few minutes)...")
    _run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"])
    _run([str(venv_python), "-m", "pip", "install", "-r", "requirements.txt"])
    marker.write_text("ok\n", encoding="utf-8")
    _log("Dependencies installed.")


def ensure_database(venv_python: Path) -> None:
    _log("Initializing database if needed...")
    _run([
        str(venv_python),
        "-c",
        "from app import app, init_db; "
        "ctx = app.app_context(); ctx.push(); init_db(); ctx.pop(); "
        "print('Database ready.')",
    ])
    (ROOT / "uploads").mkdir(exist_ok=True)


def wait_for_server(base_url: str, timeout: int) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urlopen(base_url, timeout=2) as response:
                if response.status < 500:
                    return True
        except (URLError, OSError, ValueError):
            pass
        time.sleep(1)
    return False


def start_server(venv_python: Path, port: int) -> subprocess.Popen:
    env = os.environ.copy()
    env.setdefault("LIBERTY_DEBUG", "0")
    env["PORT"] = str(port)
    env.setdefault("LIBERTY_DATABASE", str(ROOT / "film_analysis.db"))
    env.setdefault("LIBERTY_UPLOAD_FOLDER", str(ROOT / "uploads"))

    _log(f"Starting Liberty on http://127.0.0.1:{port} ...")
    return subprocess.Popen(
        [str(venv_python), "app.py"],
        cwd=ROOT,
        env=env,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch Liberty Basketball Analysis locally.")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", DEFAULT_PORT)))
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser tab.")
    parser.add_argument("--reinstall-deps", action="store_true", help="Force pip install on every run.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_url = f"http://127.0.0.1:{args.port}/"

    print()
    print("=" * 60)
    print(" Liberty Basketball — Local Test Launcher ".center(60))
    print("=" * 60)
    print()

    if args.reinstall_deps:
        marker = ROOT / ".venv" / ".liberty_deps_installed"
        if marker.exists():
            marker.unlink()

    try:
        python_cmd = ensure_python()
        ensure_git()
        ensure_ffmpeg()
        venv_python = ensure_venv(python_cmd)
        ensure_dependencies(venv_python)
        ensure_database(venv_python)
    except Exception as exc:
        _log(f"Setup failed: {exc}")
        return 1

    process = start_server(venv_python, args.port)
    try:
        if not wait_for_server(base_url, WAIT_SECONDS):
            _log("Server did not respond in time. Check output above for errors.")
            return 1

        _log(f"Server ready: {base_url}")
        if not args.no_browser:
            _log("Opening dashboard in your browser...")
            webbrowser.open(base_url)

        print()
        print("-" * 60)
        print("  Liberty is running. Begin testing:")
        print(f"    Dashboard : {base_url}")
        print(f"    Preview   : {base_url}preview")
        print(f"    Status    : {base_url}status")
        print(f"    Film      : {base_url}film")
        print(f"    Review    : {base_url}review")
        print(f"    Assistant : {base_url}assistant")
        print()
        print("  Press Ctrl+C here to stop the server.")
        print("-" * 60)
        print()

        return process.wait()
    except KeyboardInterrupt:
        _log("Stopping server...")
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        return 0


if __name__ == "__main__":
    sys.exit(main())
