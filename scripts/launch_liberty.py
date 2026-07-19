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
FILM_TOOL_TEMPLATE = ROOT / "templates" / "film_tool.html"


def resolve_demo_mode_env() -> None:
    """Enable DEMO_MODE only for a real demo package session.

    The demo bat writes ``.liberty_demo_mode`` in the package dir before launch.
    A leftover ``DEMO_MODE=1`` in the user environment (or a stray TEMP flag)
    must not turn on the DONE button for the main Documents Liberty clone.
    """
    import tempfile

    local_flag = ROOT / ".liberty_demo_mode"
    temp_flag = Path(tempfile.gettempdir()) / "LibertyDemo_mode.flag"
    if local_flag.is_file():
        os.environ["DEMO_MODE"] = "1"
        try:
            temp_flag.write_text("1\n", encoding="ascii")
        except OSError:
            pass
        _log("Demo mode enabled (.liberty_demo_mode present).")
        return

    # Main / non-demo tree: strip inherited env + stray TEMP flag.
    if "DEMO_MODE" in os.environ:
        _log("Clearing inherited DEMO_MODE (not a demo package session).")
        os.environ.pop("DEMO_MODE", None)
    if temp_flag.is_file():
        try:
            temp_flag.unlink()
            _log("Removed stray LibertyDemo_mode.flag from TEMP.")
        except OSError:
            pass


def film_tool_build_info() -> dict[str, bool | str]:
    """Read Film Tool template markers (helps catch stale repo copies)."""
    text = ""
    if FILM_TOOL_TEMPLATE.exists():
        text = FILM_TOOL_TEMPLATE.read_text(encoding="utf-8")
    return {
        "template": str(FILM_TOOL_TEMPLATE),
        "has_tagging_controls_v2": (
            'id="undoBtnBar"' in text
            and 'id="ftTagDrawerToggle"' in text
            and 'data-skip="-5"' in text
            and 'data-skip="-30"' not in text
        ),
        "has_focus_mode": "manualTagFocusBtn" in text,
    }


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
    candidates = []
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
    for source_args in (["--source", "winget"], []):
        result = subprocess.run(
            [
                "winget", "install", "-e", "--id", package_id,
                *source_args,
                "--accept-package-agreements", "--accept-source-agreements",
            ],
            cwd=ROOT,
            check=False,
        )
        if result.returncode == 0:
            return True
    return False


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


def _deps_marker() -> Path:
    return ROOT / ".venv" / ".liberty_deps_installed"


def venv_is_healthy(venv_python: Path) -> bool:
    if not venv_python.exists():
        return False
    result = subprocess.run(
        [
            str(venv_python),
            "-c",
            "import flask; from app import app; print('ok')",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def remove_venv() -> None:
    venv_dir = ROOT / ".venv"
    marker = _deps_marker()
    if marker.exists():
        marker.unlink()
    if venv_dir.exists():
        _log("Removing broken virtual environment (.venv)...")
        shutil.rmtree(venv_dir, ignore_errors=True)


def ensure_venv(python_cmd: list[str], *, recreate: bool = False) -> Path:
    venv_python = _venv_python()
    if recreate:
        remove_venv()
    elif venv_python.exists() and not venv_is_healthy(venv_python):
        _warn("Virtual environment is broken (common after OneDrive sync). Recreating .venv...")
        remove_venv()

    venv_python = _venv_python()
    if venv_python.exists():
        _log("Virtual environment already exists.")
        return venv_python

    _log("Creating virtual environment (.venv)...")
    _run(python_cmd + ["-m", "venv", str(ROOT / ".venv")])
    if not venv_python.exists():
        raise RuntimeError(f"Failed to create venv at {venv_python}")
    return venv_python


def ensure_dependencies(venv_python: Path, *, force: bool = False) -> None:
    marker = _deps_marker()
    if not force and marker.exists() and venv_is_healthy(venv_python):
        _log("Python dependencies already installed.")
        return

    if marker.exists():
        marker.unlink()
    _log("Installing Python dependencies (first run may take a few minutes)...")
    _run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"])
    _run([str(venv_python), "-m", "pip", "install", "-r", "requirements.txt"])
    if not venv_is_healthy(venv_python):
        raise RuntimeError(
            "Dependencies installed but import check failed. "
            "Try: py -3.12 scripts/launch_liberty.py --repair"
        )
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
    env.setdefault("LIBERTY_DEBUG", "1")
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
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Recreate .venv and reinstall dependencies (fixes OneDrive/corrupt venv).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_url = f"http://127.0.0.1:{args.port}/"

    print()
    print("=" * 60)
    print(" Liberty Basketball — Local Test Launcher ".center(60))
    print("=" * 60)
    print()

    resolve_demo_mode_env()

    force_deps = args.reinstall_deps or args.repair
    if force_deps:
        _deps_marker().unlink(missing_ok=True)

    try:
        python_cmd = ensure_python()
        ensure_git()
        ensure_ffmpeg()
        venv_python = ensure_venv(python_cmd, recreate=args.repair)
        ensure_dependencies(venv_python, force=force_deps)
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
        build = film_tool_build_info()
        if build["has_tagging_controls_v2"]:
            _log("Film Tool: Focus FS loaded (fullscreen video, slide-in tags, bottom controls)")
        else:
            _warn(
                "Film Tool is missing Controls v2 — git pull this repo, then restart. "
                f"Template: {build['template']}"
            )
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
        print(f"    Film build: {base_url}api/film-tool-build")
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
