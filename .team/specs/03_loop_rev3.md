VETTED by Claude Code, 2026-10-26 20:52: Scott approved Muse checking the vetter, a free gate script, cheaper Claude use, and free-model fallbacks. Coder: OpenCode. Branch: team/auto.

# Task: team loop revision 3 — Muse, gate, cheaper Claude, fallbacks

## Files
- `team_loop.ps1` (edit)
- `scripts/team_gate.py` (new)
- `tests/test_team_gate.py` (new)
- `.gitattributes` (edit: append one line)

Do not edit any other file.

## A. Gate script: scripts/team_gate.py (free, no AI, runs before Claude vets code)
Usage: `.\.venv\Scripts\python.exe scripts/team_gate.py --plan NEXT_TASK.md --baseline <score json file>`. Prints one JSON line `{"pass": true|false, "failures": [..]}`; exit 0 when pass, 1 when fail.

Checks:
1. **Files.** Files changed vs HEAD (`git status --porcelain`, tracked and untracked) must all be in the plan's `## Files` list, plus `docs/agent_handoffs/TEAM_LOG.md`, `NEXT_TASK.md`, and anything under `.team/`.
2. **Protected files** must be unchanged: `ai_analyzer.py`, `event_generator.py`, `court_memory.py`, `net_detector.py`, `manual_tag_teach.py`, `game_boxscore.py`, `scoreboard_clock.py`, `schema.sql`, `models/ball_detector.pt`, `AUTHORITY.md`, `AGENT_OPERATIONAL_PROTOCOL.md`.
3. **No changed cutoffs.** `git diff -U0 -- ai_bridge.py` must contain no removed lines (lines starting with `-` other than `---`). ai_bridge.py edits must be purely additive.
4. **applied_to_core.** No added line in any diff sets `applied_to_core` to True.
5. **Tests.** Run pytest on the plan's test files plus `tests/test_ai_bridge.py tests/test_team_score.py tests/test_build_review_page.py tests/test_team_gate.py`. They must pass.
6. **Score.** Run scripts/team_score.py. Adrian misses_called_makes must be 0, and neither film's `right` may be lower than in the baseline file.

Put each check in its own function that takes plain inputs (diff text, file lists, score dicts), so `tests/test_team_gate.py` can test them without git: a file outside the plan fails; a protected file fails; a removed ai_bridge.py line fails and a pure addition passes; `applied_to_core = True` fails; a score drop fails and an equal score passes.

In team_loop.ps1, write the score before each round to `.team/baseline_score.json` and run the gate after OpenCode codes. A gate FAIL counts as a code FAIL: send the failures to OpenCode and do not call Claude. Claude vets only after the gate passes.

## B. Cheaper Claude
Add `--model sonnet` to the plan-vet and code-vet `claude -p` calls.

## C. Muse checks the vetter
- After Claude returns `VERDICT: VETTED` (plan) or `VERDICT: PASS` (code), call Muse:
  `opencode run -m opencode/glm-5.3-flash-free "Read .team/prompt_muse.txt and follow it exactly."`
- Prompt file text: the Muse startup prompt from TEAM_RECOVERY.md section 5, plus the path of the plan, the output of `git diff` (code step only, first 20000 characters, saved to `.team/muse_diff.txt` and referenced by path), and Claude's verdict text (saved to `.team/last_claude_verdict.txt`).
- Parse `MUSE: AGREE` or `MUSE: DISAGREE: <reason>`. AGREE continues. DISAGREE stops the loop: `Stop-Loop 'MUSE DISAGREES with the vetter: <reason> (Scott decides)'`.
- No parseable answer counts as DISAGREE.

## D. Free fallbacks and waiting on limits
A call is "limited" when it fails and its output matches `429|rate limit|usage limit|quota|too many requests` (case-insensitive).
- **OpenCode coder models, in order:** `opencode/deepseek-v4.1-flash-free`, `opencode/mimo-v2.6-flash-free`, `opencode/nemotron-3.5-super-vl-free`.
- **Muse models, in order:** `opencode/glm-5.3-flash-free`, `opencode/flint-40b-free`, `opencode/beam-free`.
- **Claude limited:** use a stand-in vetter. Run `opencode run -m opencode/nemotron-3-ultra-free "Read .team/prompt_claude.txt and follow it exactly."` and log `STAND-IN VETTER (Claude limited)`. Muse still checks the stand-in.
- **Hermes limited:** no model switch; wait.
- **When every model for a step is limited:** write `WAITING for limits — retry at HH:mm` at the top of `.team/STATUS.md`, wait 60 minutes, and retry, for up to 8 hours in total. Then `Stop-Loop 'all models limited for 8 hours'`.
- Log every model switch.

## E. Stall and timeout fixes
- **Kill the whole tree.** When a call is stopped (stall or timeout), also kill its native process tree. Before `Start-Job`, record the time. After stopping, find processes named `opencode`, `node`, `claude`, or `wsl` that started after that time and run `taskkill /PID <id> /T /F` on each.
- **Hermes stall threshold.** Hermes prints nothing until it finishes, so for Hermes calls use a 40-minute stall threshold and a 45-minute hard timeout. Others stay at 20 and 30.

## F. .gitattributes
Append `*.sh text eol=lf` so `.team/run_hermes.sh` keeps LF line endings on checkout.

## Checks to run, then report (do not commit)
- `.\.venv\Scripts\python.exe -m pytest tests/test_team_gate.py tests/test_team_score.py tests/test_ai_bridge.py tests/test_build_review_page.py -q`
- PowerShell parse check of team_loop.ps1: 0 errors.
- `.\team_loop.ps1 -DryRun`: completes; prints the gate command, `--model sonnet` on both Claude calls, and both Muse calls.
- `.\.venv\Scripts\python.exe scripts/team_gate.py --plan .team/specs/03_loop_rev3.md --baseline .team/baseline_score.json` on the current working tree (create the baseline first with team_score.py), and report its JSON.

---
## Vetter feedback, revision 3.1 (Claude Code, 2026-10-26 20:58) — VETTED to fix; edit only scripts/team_gate.py, tests/test_team_gate.py, team_loop.ps1

Checked: 24 tests pass; parse 0 errors; dry run shows gate, `--model sonnet`, and both Muse calls; `.gitattributes` adds `*.sh text eol=lf`. Two fixes:

1. **Files that were already changed before the round started fail every round** (Scott's own `.gitignore`, `data/hoopsalytics/*`, and other agents' scratch files). Fix:
   - At round start, team_loop.ps1 writes `.team/round_start.json`: every path in `git status --porcelain` (tracked and untracked) with the SHA-256 of its current content (or "deleted").
   - Add `--round-start .team/round_start.json` to the gate.
   - Check 1 then fails only for a path that is NOT in the plan and is either new since round start or whose hash changed.
   - Keep check 2 (protected files) strict: a protected file fails if its hash differs from round start, or if it changed vs HEAD and was not already changed at round start.
   - Test: an already-changed, unchanged file passes; the same file with new content fails.
2. **Fail closed on missing score data.** In check_scores, a missing film, a missing `right`, or a missing `misses_called_makes` is a failure, not a skip. Also fail if Notus misses_called_makes is higher than in the baseline. Tests for each.

Run the same checks as before, plus the gate on the current tree with a round_start.json made at the start of your run. Report its JSON. Do not commit.

---
## Queued follow-ups from Muse (2026-10-26 21:38) — not yet built
1. Add `settings_store.py` (holds `ball_confidence`, a Scott gate) to the gate's protected list.
2. Save-Round: commit only the named files (`git commit -- <files>`) so anything already staged cannot ride along.
3. Use `.team/oc.sh`-style startup watchdog (no model within 2 minutes: kill and retry, 3 tries) for every OpenCode call in team_loop.ps1.
