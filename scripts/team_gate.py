#!/usr/bin/env python3
"""Free, no-AI gate that runs before Claude vets code.

Usage:
    .\\.venv\\Scripts\\python.exe scripts/team_gate.py --plan NEXT_TASK.md --baseline .team/baseline_score.json

Prints one JSON line: {"pass": true|false, "failures": [..]}
Exit 0 when pass, 1 when fail.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

PROTECTED_FILES = [
    "ai_analyzer.py",
    "event_generator.py",
    "court_memory.py",
    "net_detector.py",
    "manual_tag_teach.py",
    "game_boxscore.py",
    "scoreboard_clock.py",
    "schema.sql",
    "models/ball_detector.pt",
    "AUTHORITY.md",
    "AGENT_OPERATIONAL_PROTOCOL.md",
]

ALWAYS_ALLOWED_FILES = [
    "docs/agent_handoffs/TEAM_LOG.md",
    "NEXT_TASK.md",
]

FIXED_TEST_FILES = [
    "tests/test_ai_bridge.py",
    "tests/test_team_score.py",
    "tests/test_build_review_page.py",
    "tests/test_team_gate.py",
]

APPLIED_TO_CORE_RE = re.compile(
    r"""applied_to_core['"]?\s*[:=]\s*True\b""", re.IGNORECASE
)


def normalize_path(path: str) -> str:
    """Normalize a repo-relative path to forward slashes without a leading ./."""
    text = str(path).strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def _is_under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def hash_paths(paths: list[str], root: Path = ROOT) -> dict[str, str]:
    """Return a SHA-256 for each path, or ``deleted`` when it is not a file."""
    hashes: dict[str, str] = {}
    for path in paths:
        normalized = normalize_path(path)
        if normalized in hashes:
            continue
        try:
            data = (Path(root) / normalized).read_bytes()
        except (OSError, ValueError):
            hashes[normalized] = "deleted"
        else:
            hashes[normalized] = hashlib.sha256(data).hexdigest()
    return hashes


def parse_round_start(data: dict[str, Any]) -> dict[str, str]:
    """Normalize a round-start snapshot mapping paths to hashes."""
    return {normalize_path(str(key)): str(value) for key, value in data.items()}


def parse_plan_files(plan_text: str) -> list[str]:
    """Return the files listed in the plan's ``## Files`` section."""
    files: list[str] = []
    in_files = False
    for line in plan_text.splitlines():
        if re.match(r"^\s*##\s+Files\s*$", line):
            in_files = True
            continue
        if in_files and re.match(r"^\s*##\s+", line):
            break
        if not in_files:
            continue
        match = re.match(r"^\s*[-*]\s+`([^`]+)`", line)
        if match:
            files.append(match.group(1))
            continue
        match = re.match(r"^\s*[-*]\s+([^\s(]+)", line)
        if match:
            files.append(match.group(1))
    return files


def parse_status_lines(status_text: str) -> list[str]:
    """Parse ``git status --porcelain`` output into repo-relative paths."""
    files: list[str] = []
    for line in status_text.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        path = path.strip().strip('"')
        if path:
            files.append(normalize_path(path))
    return files


def check_files(
    changed_files: list[str],
    plan_files: list[str],
    always_allowed: list[str] | None = None,
    round_start: dict[str, str] | None = None,
    current_hashes: dict[str, str] | None = None,
) -> list[str]:
    """Unplanned files fail only when new or changed since the round started."""
    allowed = {normalize_path(path) for path in plan_files}
    if always_allowed is None:
        always_allowed = ALWAYS_ALLOWED_FILES
    allowed.update(normalize_path(path) for path in always_allowed)
    current_hashes = current_hashes or {}
    failures: list[str] = []
    for path in changed_files:
        normalized = normalize_path(path)
        if normalized in allowed:
            continue
        if _is_under(normalized, ".team"):
            continue
        if round_start is None:
            failures.append(f"changed file not in plan: {normalized}")
            continue
        if normalized not in round_start:
            failures.append(
                f"changed file not in plan (new since round start): {normalized}"
            )
        elif round_start[normalized] != current_hashes.get(normalized):
            failures.append(
                f"changed file not in plan (changed since round start): {normalized}"
            )
    return failures


def check_protected(
    changed_files: list[str],
    round_start: dict[str, str] | None = None,
    current_hashes: dict[str, str] | None = None,
) -> list[str]:
    """Protected files may not change during the round."""
    changed = {normalize_path(path) for path in changed_files}
    current_hashes = current_hashes or {}
    failures: list[str] = []
    for path in PROTECTED_FILES:
        normalized = normalize_path(path)
        if round_start is None:
            if normalized in changed:
                failures.append(f"protected file changed: {normalized}")
            continue
        if normalized in round_start:
            if round_start[normalized] != current_hashes.get(normalized):
                failures.append(f"protected file changed: {normalized}")
        elif normalized in changed:
            failures.append(f"protected file changed: {normalized}")
    return failures


def check_ai_bridge_diff(diff_text: str) -> list[str]:
    """ai_bridge.py edits must be purely additive (no removed lines)."""
    failures: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith("-") and not line.startswith("---"):
            failures.append(f"removed line in ai_bridge.py: {line}")
    return failures


def check_applied_to_core(diff_text: str) -> list[str]:
    """No added line in any diff may set applied_to_core to True."""
    failures: list[str] = []
    for line in diff_text.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        if APPLIED_TO_CORE_RE.search(line):
            failures.append(f"added line sets applied_to_core True: {line}")
    return failures


def check_scores(current: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    """Fail closed on missing score data; Adrian and Notus may not regress."""
    failures: list[str] = []
    for film in ("notus", "adrian"):
        current_film = current.get(film)
        baseline_film = baseline.get(film)
        if not isinstance(current_film, dict):
            failures.append(f"missing score data: {film}")
            current_film = None
        if not isinstance(baseline_film, dict):
            failures.append(f"missing baseline score data: {film}")
            baseline_film = None
        if current_film is not None:
            if "right" not in current_film:
                failures.append(f"missing score data: {film}.right")
            if "misses_called_makes" not in current_film:
                failures.append(f"missing score data: {film}.misses_called_makes")
        if baseline_film is not None:
            if "right" not in baseline_film:
                failures.append(f"missing baseline score data: {film}.right")
            if "misses_called_makes" not in baseline_film:
                failures.append(f"missing baseline score data: {film}.misses_called_makes")
        if (
            current_film is not None
            and baseline_film is not None
            and "right" in current_film
            and "right" in baseline_film
            and current_film["right"] < baseline_film["right"]
        ):
            failures.append(
                f"{film} right dropped from {baseline_film['right']} "
                f"to {current_film['right']}"
            )

    adrian = current.get("adrian")
    if (
        isinstance(adrian, dict)
        and "misses_called_makes" in adrian
        and adrian["misses_called_makes"] != 0
    ):
        failures.append(
            "Adrian misses_called_makes is "
            f"{adrian['misses_called_makes']}, expected 0"
        )

    notus = current.get("notus")
    baseline_notus = baseline.get("notus")
    if (
        isinstance(notus, dict)
        and "misses_called_makes" in notus
        and isinstance(baseline_notus, dict)
        and "misses_called_makes" in baseline_notus
        and notus["misses_called_makes"] > baseline_notus["misses_called_makes"]
    ):
        failures.append(
            "notus misses_called_makes rose from "
            f"{baseline_notus['misses_called_makes']} "
            f"to {notus['misses_called_makes']}"
        )
    return failures


def test_files_for_plan(plan_files: list[str]) -> list[str]:
    """Plan test files plus the fixed suite, in order and with no duplicates."""
    files: list[str] = []
    for path in plan_files:
        normalized = normalize_path(path)
        if normalized.startswith("tests/") and normalized.endswith(".py"):
            files.append(normalized)
    for path in FIXED_TEST_FILES:
        if path not in files:
            files.append(path)
    return files


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _git(*args: str) -> str:
    return _run(["git", *args]).stdout


def _last_json_line(text: str) -> Any:
    for line in reversed([ln for ln in text.splitlines() if ln.strip()]):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return None


def run_tests(test_files: list[str]) -> list[str]:
    result = _run([sys.executable, "-m", "pytest", *test_files, "-q"])
    if result.returncode == 0:
        return []
    tail = "\n".join(result.stdout.splitlines()[-20:])
    return [f"tests failed (exit {result.returncode}): {tail}"]


def run_score() -> tuple[dict[str, Any] | None, list[str]]:
    result = _run([sys.executable, str(ROOT / "scripts" / "team_score.py")])
    if result.returncode != 0:
        return None, [f"team_score.py failed (exit {result.returncode}): {result.stderr}"]
    score = _last_json_line(result.stdout)
    if not isinstance(score, dict):
        return None, [f"could not parse team_score.py output: {result.stdout}"]
    return score, []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Free team gate before Claude vets code.")
    parser.add_argument("--plan", required=True, help="Plan file with a ## Files section")
    parser.add_argument("--baseline", required=True, help="Baseline score JSON file")
    parser.add_argument(
        "--round-start",
        default=None,
        help="Round-start snapshot of changed paths and their hashes",
    )
    args = parser.parse_args(argv)

    failures: list[str] = []

    plan_path = Path(args.plan)
    try:
        plan_text = plan_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(json.dumps({"pass": False, "failures": [f"could not read plan: {exc}"]}))
        return 1
    plan_files = parse_plan_files(plan_text)

    status_text = _git("status", "--porcelain")
    changed_files = parse_status_lines(status_text)

    round_start: dict[str, str] | None = None
    if args.round_start:
        try:
            snapshot = json.loads(Path(args.round_start).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"could not read round start snapshot: {exc}")
        else:
            if isinstance(snapshot, dict):
                round_start = parse_round_start(snapshot)
            else:
                failures.append("round start snapshot is not a JSON object")

    hash_targets = list(changed_files) + list(PROTECTED_FILES)
    current_hashes = hash_paths(hash_targets)

    failures.extend(
        check_files(changed_files, plan_files, round_start=round_start, current_hashes=current_hashes)
    )
    failures.extend(
        check_protected(changed_files, round_start=round_start, current_hashes=current_hashes)
    )

    bridge_diff = _git("diff", "-U0", "--", "ai_bridge.py")
    failures.extend(check_ai_bridge_diff(bridge_diff))

    all_diff = "\n".join(
        [
            _git("diff", "-U0"),
            _git("diff", "--cached", "-U0"),
        ]
    )
    failures.extend(check_applied_to_core(all_diff))

    failures.extend(run_tests(test_files_for_plan(plan_files)))

    current_score, score_failures = run_score()
    failures.extend(score_failures)
    if current_score is not None:
        try:
            baseline_score = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"could not read baseline score: {exc}")
        else:
            failures.extend(check_scores(current_score, baseline_score))

    passed = not failures
    print(json.dumps({"pass": passed, "failures": failures}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
