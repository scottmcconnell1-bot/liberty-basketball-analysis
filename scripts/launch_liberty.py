#!/usr/bin/env python3
"""
One-click local launcher for Liberty Basketball Analysis.

Checks prerequisites, prefers a CUDA-capable Python (system 3.12 with torch)
over a torch-less .venv, initializes the DB, starts the Flask app, and opens
the dashboard in your browser.

Usage:
  python scripts/launch_liberty.py
  python scripts/launch_liberty.py --port 8081 --no-browser

Windows: double-click ``Start Liberty.bat`` in the repo root.
Linux:   bash scripts/launch_liberty.sh
"""

from __future__ import annotations

import argparse
import json
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


def _system_python_candidates() -> list[list[str]]:
    if os.name == "nt":
        return [
            ["py", "-3.12"],
            ["py", "-3.13"],
            ["python"],
            ["python3"],
        ]
    return [
        ["python3.12"],
        ["python3.13"],
        ["python3"],
        ["python"],
    ]


def _find_system_python() -> list[str]:
    for cmd in _system_python_candidates():
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


def _probe_interpreter(cmd: list[str]) -> dict | None:
    """Probe version, app import, and torch CUDA for an interpreter."""
    probe = (
        "import json, sys\n"
        "info = {"
        " 'exe': sys.executable,"
        " 'version': '.'.join(map(str, sys.version_info[:3])),"
        " 'app_ok': False,"
        " 'torch': None,"
        " 'cuda': False,"
        "}\n"
        "try:\n"
        "    ver = tuple(sys.version_info[:2])\n"
        "    info['version_ok'] = (3, 12) <= ver <= (3, 13)\n"
        "except Exception:\n"
        "    info['version_ok'] = False\n"
        "try:\n"
        "    import flask  # noqa: F401\n"
        "    from app import app  # noqa: F401\n"
        "    info['app_ok'] = True\n"
        "except Exception as e:\n"
        "    info['app_err'] = type(e).__name__\n"
        "try:\n"
        "    import torch\n"
        "    info['torch'] = str(torch.__version__)\n"
        "    info['cuda'] = bool(torch.cuda.is_available())\n"
        "except Exception:\n"
        "    pass\n"
        "print(json.dumps(info))\n"
    )
    try:
        result = subprocess.run(
            cmd + ["-c", probe],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    line = (result.stdout or "").strip().splitlines()
    if not line:
        return None
    try:
        return json.loads(line[-1])
    except json.JSONDecodeError:
        return None


def _cmd_key(cmd: list[str]) -> str:
    return " ".join(cmd)


def resolve_runtime_python(venv_python: Path | None) -> list[str] | None:
    """
    Prefer an interpreter where torch.cuda.is_available() is True.

    Order:
      1. .venv if it has CUDA torch and can import the app
      2. system py -3.12 / Python 3.12+ with CUDA torch and app import
      3. .venv if healthy (no CUDA)
      4. system Python that can import the app
    """
    candidates: list[tuple[str, list[str]]] = []
    seen: set[str] = set()

    def _add(kind: str, cmd: list[str]) -> None:
        key = _cmd_key(cmd)
        if key in seen:
            return
        if shutil.which(cmd[0]) is None and kind != "venv":
            return
        if kind == "venv" and not Path(cmd[0]).exists():
            return
        seen.add(key)
        candidates.append((kind, cmd))

    if venv_python is not None:
        _add("venv", [str(venv_python)])
    for cmd in _system_python_candidates():
        _add("system", cmd)

    probed: list[tuple[str, list[str], dict]] = []
    for kind, cmd in candidates:
        info = _probe_interpreter(cmd)
        if not info:
            _log(f"Probe skip: {_cmd_key(cmd)} (not usable)")
            continue
        if not info.get("version_ok", False):
            _log(f"Probe skip: {_cmd_key(cmd)} (Python {info.get('version')} out of range)")
            continue
        probed.append((kind, cmd, info))
        _log(
            f"Probe {_cmd_key(cmd)}: exe={info.get('exe')} "
            f"torch={info.get('torch')} cuda={info.get('cuda')} app_ok={info.get('app_ok')}"
        )

    def _pick(predicate) -> tuple[str, list[str], dict] | None:
        for item in probed:
            if predicate(*item):
                return item
        return None

    chosen = (
        _pick(lambda k, _c, i: k == "venv" and i.get("cuda") and i.get("app_ok"))
        or _pick(lambda k, _c, i: k == "system" and i.get("cuda") and i.get("app_ok"))
        or _pick(lambda _k, _c, i: i.get("cuda") and i.get("app_ok"))
        or _pick(lambda k, _c, i: k == "venv" and i.get("app_ok"))
        or _pick(lambda k, _c, i: k == "system" and i.get("app_ok"))
        or _pick(lambda _k, _c, i: i.get("app_ok"))
    )
    if not chosen:
        return None

    kind, cmd, info = chosen
    exe = info.get("exe") or _cmd_key(cmd)
    torch_v = info.get("torch") or "none"
    cuda = bool(info.get("cuda"))
    _log(f"Runtime Python: {exe} (torch={torch_v}, cuda={cuda}, source={kind})")
    if not cuda:
        _warn(
            "CUDA torch not available on the selected interpreter. "
            "GPU analysis will fall back to CPU. "
            "Install torch with CUDA on Python 3.12, or recreate .venv with CUDA torch."
        )
    return cmd


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
        _log(f"Bootstrap Python: {' '.join(cmd)}")
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


def ensure_database(python_cmd: list[str]) -> None:
    _log("Initializing database if needed...")
    _run([
        *python_cmd,
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


def start_server(python_cmd: list[str], port: int) -> subprocess.Popen:
    env = os.environ.copy()
    env.setdefault("LIBERTY_DEBUG", "1")
    env["PORT"] = str(port)
    env.setdefault("LIBERTY_DATABASE", str(ROOT / "film_analysis.db"))
    env.setdefault("LIBERTY_UPLOAD_FOLDER", str(ROOT / "uploads"))

    _log(f"Starting Liberty on http://127.0.0.1:{port} ...")
    return subprocess.Popen(
        [*python_cmd, "app.py"],
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

    force_deps = args.reinstall_deps or args.repair
    if force_deps:
        _deps_marker().unlink(missing_ok=True)

    try:
        python_cmd = ensure_python()
        ensure_git()
        ensure_ffmpeg()

        venv_path = _venv_python()
        # Prefer CUDA system Python over a torch-less .venv when both exist.
        runtime = resolve_runtime_python(venv_path if venv_path.exists() else None)

        if args.repair or force_deps or runtime is None:
            venv_python = ensure_venv(python_cmd, recreate=args.repair)
            ensure_dependencies(venv_python, force=force_deps or args.repair)
            runtime = resolve_runtime_python(venv_python) or [str(venv_python)]
        # else: keep selected runtime (typically system Python 3.12 + CUDA torch)

        ensure_database(runtime)
    except Exception as exc:
        _log(f"Setup failed: {exc}")
        return 1

    process = start_server(runtime, args.port)
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
