#!/usr/bin/env python3
"""Copy Git LFS model pointers in models/ to real .pt weight files."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = ROOT / "models"
POINTER_RE = re.compile(
    r"^version https://git-lfs\.github\.com/spec/v1\n"
    r"oid sha256:([0-9a-f]{64})\n"
    r"size (\d+)\n?$",
    re.MULTILINE,
)


def _log(message: str) -> None:
    print(f"[liberty-models] {message}", flush=True)


def _is_pointer(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return text.startswith("version https://git-lfs.github.com/spec/v1")


def _parse_pointer(path: Path) -> tuple[str, int] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = POINTER_RE.match(text)
    if not match:
        return None
    return match.group(1), int(match.group(2))


def _lfs_object_path(oid: str) -> Path:
    return ROOT / ".git" / "lfs" / "objects" / oid[:2] / oid[2:4] / oid


def _git_lfs_fetch() -> bool:
    if not shutil.which("git"):
        _log("git not found on PATH")
        return False
    _log("Fetching Git LFS objects...")
    result = subprocess.run(
        ["git", "lfs", "fetch", "--include=models/*.pt"],
        cwd=ROOT,
        check=False,
    )
    if result.returncode != 0:
        result = subprocess.run(["git", "lfs", "fetch", "--all"], cwd=ROOT, check=False)
    return result.returncode == 0


def materialize_model(path: Path, *, fetch: bool = True) -> tuple[bool, str]:
    rel = path.relative_to(ROOT)
    if not path.exists():
        return False, f"{rel} not found"

    pointer = _parse_pointer(path)
    if pointer is None:
        size = path.stat().st_size
        if size > 10_000:
            return True, f"{rel} already materialized ({size:,} bytes)"
        return False, f"{rel} is too small and not a Git LFS pointer ({size} bytes)"

    oid, expected_size = pointer
    object_path = _lfs_object_path(oid)
    if not object_path.exists():
        if fetch and _git_lfs_fetch():
            object_path = _lfs_object_path(oid)
        if not object_path.exists():
            return False, (
                f"{rel} needs Git LFS object {oid[:12]}… Run: "
                "git lfs install && git lfs fetch --all && python scripts/materialize_lfs_models.py"
            )

    actual_size = object_path.stat().st_size
    if actual_size != expected_size:
        return False, f"{rel} LFS object size mismatch (expected {expected_size}, got {actual_size})"

    shutil.copy2(object_path, path)
    return True, f"{rel} materialized ({actual_size:,} bytes)"


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    fetch = "--no-fetch" not in argv
    paths = [Path(arg) for arg in argv if not arg.startswith("-")]
    if not paths:
        paths = sorted(MODELS_DIR.glob("*.pt"))

    if not paths:
        _log("No model files found.")
        return 1

    ok_count = 0
    for path in paths:
        ok, message = materialize_model(path.resolve(), fetch=fetch)
        _log(message)
        if ok:
            ok_count += 1

    return 0 if ok_count == len(paths) else 1


if __name__ == "__main__":
    raise SystemExit(main())
