#!/usr/bin/env python3
"""Refuse a change that crosses one of Scott's gates without saying so out loud.

The project's own notes list things that stop and wait for Scott: `schema.sql`, the
ball weights and `ball_confidence`, a feature flag going False to True, unpausing
the teach loop or auto-accept, and deleting data without an archive plan. Those
rules live in prose, and prose does not run. This does.

    python scripts/check_scott_gates.py --base origin/main --head HEAD
    python scripts/check_scott_gates.py --base origin/main --head HEAD --body-file body.txt

Exit status 1 means at least one blocking finding. Nothing here decides whether a
change is *right* -- only whether it is the kind of change that has to be named and
approved before it lands.

**How to get past a gate.** Put a line in the pull request body naming what you are
crossing, for each one:

    Scott approved: schema.sql — adds the possession index, Scott said yes 2026-10-11

The token after the colon has to appear in the finding, so a blanket "Scott approved:
everything" does not clear a specific file. This is an honesty rail, not a lock: it
makes an approved change visible in the pull request where a reviewer reads it.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Paths that are a Scott decision on their own. The flag is whether crossing it
# blocks, or only prints -- a workflow change should be noticed, not refused.
GATED_PATHS = (
    ("schema.sql", "the database schema", True),
    ("models/", "a model weights file", True),
    ("encrypted-archive/", "the encrypted archive", True),
    (".github/workflows/", "what runs on every pull request", False),
)

# Settings whose value is a Scott decision. Matched on changed lines in the diff.
GATED_SETTINGS = (
    ("ball_confidence", "the ball detector's confidence floor"),
    ("ball_detector_model", "which ball weights the analyzer loads"),
    ("auto_accept_event_confidence", "auto-accept: it promotes AI rows with no human review"),
    ("shot_min_ball_rise", "the primary shot gate (80 px)"),
    ("live_shot_min_ball_rise", "the live field-goal gate (170 px), the one Scott refused to drop"),
    ("make_min_gap_frames", "what counts as a made basket"),
    ("emit_fouls", "the foul heuristic Scott kept opt-in"),
)

# Files that must never be committed: credentials, the database, the answer key.
NEVER_COMMIT = (
    (re.compile(r"(^|/)film_analysis\.db$"), "the database. Home owns it; it is not in git"),
    (re.compile(r"(^|/)\.env$"), "a credential file"),
    (re.compile(r"scottmcconnell1-bot-liberty-basketball-analysis.*\.txt$"),
     "the GitHub credential file"),
    (re.compile(r"^data/film_tags/.*\.json$"),
     "the coach's tags: the answer key, and it carries the roster"),
    (re.compile(r"^uploads/.*\.(mp4|mov|mkv)$"), "game film. Home owns the films"),
)

# Touch the way a shot is read and the pull request has to carry a score.
SCORING_FILES = (
    "net_detector.py", "event_generator.py", "ai_bridge.py", "stat_rules.py",
    "manual_tag_teach.py", "shot_tag_gate.py", "ai_analyzer.py", "court_memory.py",
)
SCORE_LINE = re.compile(
    r"right\s*=\s*\d+.*makes_missed\s*=\s*\d+.*misses_called_makes\s*=\s*\d+", re.I)

# Hermes edits ai_bridge.py only.
HERMES_BRANCH = re.compile(r"hermes", re.I)
HERMES_ALLOWED = ("ai_bridge.py", "docs/", "tests/", "benchmarks/", "scripts/")

APPROVAL = re.compile(r"^\s*Scott approved:\s*(.+)$", re.I | re.M)


class Finding:
    def __init__(self, rule: str, token: str, message: str, blocking: bool = True):
        self.rule, self.token, self.message, self.blocking = rule, token, message, blocking

    def __repr__(self) -> str:
        return f"{'BLOCK' if self.blocking else ' WARN'}  [{self.rule}] {self.message}"


# Prose cannot change a setting. Settings rules read these file types only.
CODE_SUFFIXES = (".py", ".sql", ".json", ".yml", ".yaml", ".toml", ".cfg", ".ini",
                 ".js", ".ts", ".ps1", ".sh")

# Files that name the gated settings for a living, and so must not be read as
# changing them: this checker's own rule table, and tests. A real change to a
# setting always also touches the file that defines or reads it, which is still
# scanned, so nothing is lost by skipping these.
SETTINGS_SCAN_SKIP = ("scripts/check_scott_gates.py", "tests/")


def _scan_for_settings(path: str) -> bool:
    return path.endswith(CODE_SUFFIXES) and not path.startswith(SETTINGS_SCAN_SKIP) \
        and path not in SETTINGS_SCAN_SKIP


def code_diff_lines(diff_text: str) -> list[str]:
    """Added and removed lines from a unified diff, from files a setting can live in.

    Tracks the ``+++ b/<path>`` header so each hunk is attributed to its file, then
    drops hunks belonging to documentation, to this checker's own rule table and to
    tests. Without the first, a plan document that quotes a gated setting reads as a
    change to it; without the second, this checker blocks every change to itself.
    """
    lines: list[str] = []
    in_code = False
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            path = path[2:] if path.startswith(("a/", "b/")) else path
            in_code = _scan_for_settings(path)
            continue
        if line.startswith(("---", "diff ", "index ", "@@")):
            continue
        if in_code and line.startswith(("+", "-")):
            lines.append(line)
    return lines


def approvals(body: str) -> list[str]:
    return [m.strip().lower() for m in APPROVAL.findall(body or "")]


def _approved(finding: Finding, granted: list[str]) -> bool:
    token = finding.token.lower()
    return any(token in line for line in granted)


def review(changed: list[str], added: list[str], removed: list[str],
           diff_text: str, body: str, branch: str) -> list[Finding]:
    """Every finding for this change. Pure: no git, no network."""
    findings: list[Finding] = []

    for path in changed:
        for prefix, what, blocking in GATED_PATHS:
            if path == prefix or path.startswith(prefix):
                findings.append(Finding(
                    "gated-path", prefix,
                    f"{path} changes {what}." + (" That is a Scott gate." if blocking else ""),
                    blocking=blocking))

    for path in added:
        for pattern, what in NEVER_COMMIT:
            if pattern.search(path):
                findings.append(Finding(
                    "never-commit", path,
                    f"{path} is {what}. Do not commit it."))

    # Only code counts for the settings rules. A plan document that explains what
    # live_shot_min_ball_rise does is not a change to it, and a checker that cannot
    # tell the difference gets switched off within a week.
    changed_lines = code_diff_lines(diff_text)
    for key, what in GATED_SETTINGS:
        if any(key in ln for ln in changed_lines):
            findings.append(Finding(
                "gated-setting", key,
                f"this change touches {key}: {what}. That is a Scott gate."))

    # A flag going False -> True turns something on. Match per key, not per file.
    off = {m.group(1) for ln in changed_lines if ln.startswith("-")
           for m in [re.search(r'"([a-z_]+)"\s*:\s*False', ln)] if m}
    on = {m.group(1) for ln in changed_lines if ln.startswith("+")
          for m in [re.search(r'"([a-z_]+)"\s*:\s*True', ln)] if m}
    for key in sorted(off & on):
        findings.append(Finding(
            "flag-flip", key,
            f'"{key}" goes False to True. Turning a feature on is a Scott gate.'))

    for path in removed:
        if path.startswith(("data/", "tag-exports/", "benchmarks/")):
            findings.append(Finding(
                "deleted-data", path,
                f"{path} is deleted. Deleting data needs an archive plan first."))

    touched_scoring = sorted(p for p in changed if p in SCORING_FILES)
    if touched_scoring and not SCORE_LINE.search(body or ""):
        findings.append(Finding(
            "no-score", "no-score",
            f"this change touches {', '.join(touched_scoring)} but the body carries no score. "
            "A note that says a rule is implemented is not a result. Run "
            "scripts/shot_tag_score.py and paste the line: "
            "right=N makes_missed=N misses_called_makes=N"))

    if HERMES_BRANCH.search(branch or ""):
        strays = sorted(p for p in changed
                        if not p.startswith(HERMES_ALLOWED) and p not in HERMES_ALLOWED)
        if strays:
            findings.append(Finding(
                "hermes-boundary", "hermes-boundary",
                f"branch {branch} looks like a Hermes branch, which edits ai_bridge.py only, "
                f"but it changes {', '.join(strays)}."))

    granted = approvals(body)
    return [f for f in findings if not (f.blocking and _approved(f, granted))]


def _git(*args: str) -> str:
    done = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if done.returncode:
        raise SystemExit(
            f"git {' '.join(args)} failed: {done.stderr.strip() or done.returncode}\n"
            "A ref that is not fetched yet is the usual cause; try git fetch origin first.")
    return done.stdout


def diff_range(base: str, head: str) -> str:
    """``base...head`` normally; ``base..head`` when the two share no history.

    Scott_Hermes has no merge base with main, and a checker that crashes on the one
    branch people most want checked is no use.
    """
    probe = subprocess.run(["git", "merge-base", base, head], cwd=ROOT,
                           capture_output=True, text=True)
    return f"{base}...{head}" if probe.returncode == 0 else f"{base}..{head}"


def from_git(base: str, head: str) -> tuple[list[str], list[str], list[str], str]:
    rng = diff_range(base, head)
    status = [ln.split("\t") for ln in _git("diff", "--name-status", rng).splitlines() if ln]
    changed = [parts[-1] for parts in status]
    added = [parts[-1] for parts in status if parts[0].startswith("A")]
    removed = [parts[-1] for parts in status if parts[0].startswith("D")]
    return changed, added, removed, _git("diff", "--unified=0", rng)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--body-file", type=Path, help="pull request body; '-' for stdin")
    ap.add_argument("--branch", default="")
    args = ap.parse_args(argv)

    body = ""
    if args.body_file:
        body = sys.stdin.read() if str(args.body_file) == "-" else \
            args.body_file.read_text(encoding="utf-8")
    branch = args.branch or _git("rev-parse", "--abbrev-ref", "HEAD").strip()

    changed, added, removed, diff_text = from_git(args.base, args.head)
    findings = review(changed, added, removed, diff_text, body, branch)

    print(f"{len(changed)} files changed between {args.base} and {args.head}, "
          f"branch {branch}")
    if not findings:
        print("No gate crossed.")
        return 0
    for finding in findings:
        print(finding)
    blocking = [f for f in findings if f.blocking]
    if blocking:
        print(f"\n{len(blocking)} gate(s) crossed without approval. Name each one in the "
              "pull request body as:\n    Scott approved: <token> — why, and when he said it")
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
