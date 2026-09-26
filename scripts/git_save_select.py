#!/usr/bin/env python3
"""Pick the paths the nightly daily_git_save.ps1 may stage (an ALLOWLIST).

The old script ran `git add -A` and then tried to peel runtime files back off,
which pushed a Chrome Local Storage copy, Flask logs and scratch screenshots.
This helper inverts that: only source/doc files under known folders (plus a
few named data files) are ever returned; everything else is skipped.

Usage (what daily_git_save.ps1 runs):
  py -3.12 scripts/git_save_select.py --repo . --out <file>
The file gets the selected paths NUL-separated, for
  git --literal-pathspecs add --pathspec-from-file=<file> --pathspec-file-nul
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path, PurePosixPath

# Never stage files bigger than this (weights, videos, DB copies, bundles).
MAX_BYTES = 1_000_000

# Exact repo paths that are always allowed (when not a secret, see DENY rules).
ALLOWED_EXACT = {
    "docs/LEARNING_STATUS.md",
    "data/hoopsalytics/full_film_panel_targets.json",
}

SOURCE_EXTS = {
    ".py", ".md", ".txt", ".sql", ".ini", ".toml", ".cfg", ".bat", ".ps1", ".sh",
    ".html", ".js", ".css", ".json", ".yml", ".yaml", ".service", ".conf", ".svg",
}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg", ".woff", ".woff2"}

# Top-level folders that hold source/docs, and the extensions allowed in each.
ALLOWED_DIRS: dict[str, set[str]] = {
    "blueprints": SOURCE_EXTS,
    "templates": SOURCE_EXTS,
    "static": SOURCE_EXTS | IMAGE_EXTS,
    "scripts": SOURCE_EXTS,
    "tests": SOURCE_EXTS | {".csv"},
    "docs": SOURCE_EXTS | IMAGE_EXTS,
    "deploy": SOURCE_EXTS,
    "services": SOURCE_EXTS,
    "src": SOURCE_EXTS,
    "stat_book": SOURCE_EXTS,
}
# Root-level files: source/config only (root *.json / *.html are mostly scratch output).
ROOT_EXTS = {".py", ".md", ".txt", ".sql", ".ini", ".toml", ".cfg", ".bat", ".ps1", ".sh", ".yml", ".yaml"}
ROOT_NAMES = {".gitignore", ".gitattributes", "Dockerfile", "package.json", "package-lock.json"}
# Already-tracked learned model configs may be updated, never new files there.
TRACKED_ONLY_GLOBS = ("models/*.json",)
# Library code that lives next to tag exports (only .py directly in the folder).
TAG_EXPORT_SOURCE = ("tag-exports", {".py"})

DENY_DIRS = {"data", "uploads", "logs", "node_modules", "__pycache__", ".git", ".claude", "backup", "backups"}
DENY_EXTS = {".log", ".db", ".sqlite", ".sqlite3", ".pem", ".pfx", ".p12", ".key", ".pt", ".mp4", ".npy", ".pkl"}
DENY_NAMES = {"credentials.json", "teach_loop_state.json", "full_film_panel_latest.json",
              "full_film_panel_history.jsonl", "detached_pids.json"}


def denied(rel: str) -> bool:
    p = PurePosixPath(rel)
    parts = p.parts
    name = p.name.lower()
    if rel in ALLOWED_EXACT:
        return False
    if any(part.startswith(("_tmp", "_chrome", "_review")) for part in parts):
        return True
    if name == ".env" or name.startswith(".env."):
        return True
    if name in DENY_NAMES:
        return True
    suffixes = [s.lower() for s in p.suffixes]
    if any(s in DENY_EXTS for s in suffixes) or any(s.startswith((".db-", ".sqlite-")) for s in suffixes):
        return True
    if name.endswith((".err", ".out")):
        return True
    return any(part.lower() in DENY_DIRS for part in parts[:-1])


def allowed(rel: str, *, tracked: bool) -> bool:
    if denied(rel):
        return False
    if rel in ALLOWED_EXACT:
        return True
    p = PurePosixPath(rel)
    ext = p.suffix.lower()
    if len(p.parts) == 1:
        return p.name in ROOT_NAMES or ext in ROOT_EXTS
    top = p.parts[0]
    if top in ALLOWED_DIRS:
        return ext in ALLOWED_DIRS[top]
    if top == TAG_EXPORT_SOURCE[0]:
        return len(p.parts) == 2 and ext in TAG_EXPORT_SOURCE[1]
    if tracked and any(p.match(g) for g in TRACKED_ONLY_GLOBS):
        return True
    return False


def parse_porcelain_z(data: str) -> list[tuple[str, str]]:
    """[(XY, path)] from `git status --porcelain=v1 -z`; renames yield new and old path."""
    out: list[tuple[str, str]] = []
    tokens = data.split("\0")
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        i += 1
        if len(tok) < 4:
            continue
        xy, path = tok[:2], tok[3:]
        out.append((xy, path))
        if "R" in xy or "C" in xy:
            if i < len(tokens) and tokens[i]:
                out.append((xy, tokens[i]))  # the old path (its deletion is staged too)
            i += 1
    return out


def select_paths(repo: Path, porcelain: str | None = None) -> tuple[list[str], list[str]]:
    """(selected, skipped) repo-relative paths for this working tree."""
    if porcelain is None:
        porcelain = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=str(repo), check=True, capture_output=True, text=True, encoding="utf-8",
        ).stdout
    selected: list[str] = []
    skipped: list[str] = []
    for xy, rel in parse_porcelain_z(porcelain):
        tracked = xy != "??"
        full = Path(repo) / rel
        ok = allowed(rel, tracked=tracked)
        if ok and full.is_file() and full.stat().st_size > MAX_BYTES:
            ok = False
        (selected if ok else skipped).append(rel)
    return sorted(set(selected)), sorted(set(skipped))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--out", type=Path, required=True, help="NUL-separated pathspec file to write")
    args = ap.parse_args(argv)
    selected, skipped = select_paths(args.repo)
    args.out.write_bytes(b"".join(p.encode("utf-8") + b"\0" for p in selected))
    print(f"selected {len(selected)} path(s); skipped {len(skipped)} not on the allowlist")
    for rel in skipped[:50]:
        print(f"  skip: {rel}")
    if len(skipped) > 50:
        print(f"  ... and {len(skipped) - 50} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
