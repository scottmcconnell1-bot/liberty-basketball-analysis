#!/usr/bin/env python3
"""Text UI installer for Liberty Basketball Analysis."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUNDLE_SCRIPT = ROOT / "scripts" / "build_transfer_bundle.sh"


def clear_screen() -> None:
    print("\033c", end="")


def pause() -> None:
    input("\nPress Enter to continue...")


def venv_bin(name: str) -> Path:
    scripts_dir = "Scripts" if os.name == "nt" else "bin"
    return ROOT / ".venv" / scripts_dir / name


def run(cmd: list[str], *, env: dict[str, str] | None = None) -> None:
    print(f"\n$ {' '.join(cmd)}\n")
    subprocess.run(cmd, cwd=ROOT, check=True, env=env)


def has_nvidia_gpu() -> bool:
    return shutil.which("nvidia-smi") is not None


def docker_compose_available() -> bool:
    if shutil.which("docker") is None:
        return False
    result = subprocess.run(
        ["docker", "compose", "version"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def render_header() -> None:
    gpu_state = "detected" if has_nvidia_gpu() else "not detected"
    print("=" * 72)
    print(" Liberty Basketball Analysis Setup ".center(72, "="))
    print("=" * 72)
    print(f"Project root : {ROOT}")
    print(f"NVIDIA GPU   : {gpu_state}")
    print()
    print("Choose how you want to install or package the project.")
    print()


def install_standalone() -> None:
    python_bin = sys.executable
    clear_screen()
    render_header()
    print("[Standalone install]")
    print("- Creates/updates .venv")
    print("- Installs requirements.txt")
    print("- Creates uploads/ and initializes the SQLite schema")
    print()

    run([python_bin, "-m", "venv", str(ROOT / ".venv")])
    run([str(venv_bin("python")), "-m", "pip", "install", "--upgrade", "pip"])
    run([str(venv_bin("pip")), "install", "-r", "requirements.txt"])
    (ROOT / "uploads").mkdir(exist_ok=True)
    run([
        str(venv_bin("python")),
        "-c",
        "from app import app, init_db; "
        "ctx = app.app_context(); ctx.push(); init_db(); ctx.pop(); "
        "print('Database initialized.')",
    ])

    print("\nStandalone install complete.")
    print(f"Start command: {venv_bin('python')} app.py")
    print("Production example: LIBERTY_DEBUG=0 PORT=8080 .venv/bin/python app.py")
    pause()


def install_container(use_gpu: bool | None = None) -> None:
    clear_screen()
    render_header()
    if not docker_compose_available():
        raise RuntimeError("docker compose is required for the container install path.")

    if use_gpu is None:
        use_gpu = has_nvidia_gpu()

    compose_files = ["docker-compose.yml"]
    if use_gpu:
        compose_files.append("docker-compose.gpu.yml")

    compose_cmd = ["docker", "compose"]
    for compose_file in compose_files:
        compose_cmd.extend(["-f", compose_file])

    print("[Container install]")
    print(f"- Compose files: {', '.join(compose_files)}")
    print("- Builds the image and starts the service in the background")
    print()

    run(compose_cmd + ["up", "-d", "--build"])

    print("\nContainer install complete.")
    print("View logs with:")
    print("  " + " ".join(compose_cmd + ["logs", "-f"]))
    pause()


def build_transfer_bundle() -> None:
    clear_screen()
    render_header()
    if not BUNDLE_SCRIPT.exists():
        raise RuntimeError(f"Bundle script not found: {BUNDLE_SCRIPT}")
    run(["bash", str(BUNDLE_SCRIPT)])
    pause()


def main() -> int:
    actions = {
        "1": ("Install standalone", install_standalone),
        "2": ("Install container (auto-detect CPU/GPU)", lambda: install_container(None)),
        "3": ("Install container (CPU only)", lambda: install_container(False)),
        "4": ("Install container (GPU override)", lambda: install_container(True)),
        "5": ("Build transfer bundle", build_transfer_bundle),
        "q": ("Quit", None),
    }

    while True:
        clear_screen()
        render_header()
        for key, (label, _) in actions.items():
            print(f"  [{key}] {label}")
        print()

        choice = input("Select an option: ").strip().lower()
        if choice == "q":
            return 0
        if choice not in actions:
            print("\nInvalid selection.")
            pause()
            continue

        _, action = actions[choice]
        try:
            if action:
                action()
        except subprocess.CalledProcessError as exc:
            print(f"\nCommand failed with exit code {exc.returncode}.")
            pause()
        except Exception as exc:  # pragma: no cover - interactive script path
            print(f"\n{exc}")
            pause()


if __name__ == "__main__":
    raise SystemExit(main())
