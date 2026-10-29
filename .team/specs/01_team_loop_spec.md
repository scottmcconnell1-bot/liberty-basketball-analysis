VETTED by Claude Code, 2026-10-26: design approved by Scott (C:\Users\scott\Documents\Team_Loop_Design_2026-10-26.md). Coder: OpenCode. Branch: team/auto. Scores below reproduced with run_saved_v6_rule today (Notus 24/31/7/0, Adrian 99/111/12/0).

# Task: build the team loop (relay)

## Files (create only these; do not edit or delete any other file)
- `team_loop.ps1` (repo root, new)
- `.team/run_hermes.sh` (new; must be saved with LF line endings)
- `scripts/team_score.py` (new)
- `tests/test_team_score.py` (new)

`docs/agent_handoffs/TEAM_LOG.md` is created by the script at run time if missing. Do not touch `run_agent_pipeline.ps1`, `ai_bridge.py`, or any doc.

## 1. scripts/team_score.py
Prints ONE JSON line with the make/miss score on both films:
`{"notus": {"right": 24, "total": 31, "makes_missed": 7, "misses_called_makes": 0}, "adrian": {...}, "goal_reached": false}`
- Notus tracks: `gemini-upload/notus_q1_v6_tracks.json` (repo).
- Adrian tracks: `%TEMP%\v6_tracks.json`; if missing, `C:\Users\scott\Documents\liberty_offline_backup\temp_scoring\v6_tracks.json`. If neither exists, exit code 2 with a clear message.
- For each file: `rows = json.load(...)`; `times = [r["t"] for r in rows if r.get("hoop") and len(r["hoop"]) == 4]`; `s = ai_bridge.run_saved_v6_rule(times, path)`; use `s["right"], s["total_tags"], s["makes_missed"], s["misses_called_makes"]`.
- `run_saved_v6_rule` prints its own lines; capture/suppress stdout during the call so the JSON line is the only output.
- `goal_reached` = notus right == notus total AND adrian misses_called_makes == 0 AND adrian makes_missed <= 12.
- `tests/test_team_score.py`: run the scorer function on the Notus file and assert right 24, total 31, makes_missed 7, misses_called_makes 0; assert goal_reached is False. Skip the Adrian part if its tracks are missing.

## 2. .team/run_hermes.sh
```bash
#!/usr/bin/env bash
# Usage: run_hermes.sh <prompt file (Linux path)>
cd /mnt/c/Users/scott/Documents/liberty-basketball-analysis || exit 1
hermes chat -q "$(cat "$1")"
```

## 3. team_loop.ps1
Parameters: `-MaxRounds 10`, `-MaxNoProgress 3`, `-DryRun` (switch).
Writes every step to `docs/agent_handoffs/TEAM_LOG.md` as `### <yyyy-MM-dd HH:mm:ss> <Agent> — <what happened>` plus a short body.

Start:
1. `Set-Location` the repo. `git switch team/auto` (create it with `git switch -c team/auto` if missing). Refuse to run on `main`.
2. Run `scripts/team_score.py`; record the baseline score in the log.

Each round (1..MaxRounds):
1. **Hermes plans.** Write the prompt to `.team/prompt_hermes.txt` (UTF-8, no BOM) and run
   `wsl --exec bash -l /mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/run_hermes.sh /mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/prompt_hermes.txt`.
   Prompt: the Hermes startup prompt in TEAM_RECOVERY.md section 5, plus: read the last 200 lines of TEAM_LOG.md; include a "## Files" section listing every file to change; if the goal is reached or no task fits, write `.team/STOP.md` whose first line is exactly one of `GOAL_REACHED`, `SCOTT_GATE`, `CANNOT_REACH`, followed by the reason, instead of NEXT_TASK.md.
2. If `.team/STOP.md` exists: `CANNOT_REACH` triggers ONE brainstorm round (below) per stall and then step 1 again; a second `CANNOT_REACH` after a brainstorm, or `GOAL_REACHED`/`SCOTT_GATE`, stops the loop.
3. **Claude vets the plan.** Run
   `claude -p <prompt> --allowedTools "Read" "Grep" "Glob" "Bash(git diff:*)" "Bash(git log:*)" "Edit(NEXT_TASK.md)"`.
   Prompt: vet NEXT_TASK.md against TEAM_RECOVERY.md, CLAUDE.md, AUTHORITY.md, AGENT_OPERATIONAL_PROTOCOL.md, ACTIVE.md, OLLAMA.md, DETECTOR_PROPOSAL_REJECTION.md; stamp the first line of NEXT_TASK.md `VETTED by Claude Code, <date>: <reason>` or `REJECTED by Claude Code, <date>: <reason>`; end the reply with a line `VERDICT: VETTED` or `VERDICT: REJECTED`.
   REJECTED: append the reason to the log and go back to step 1 (max 2 rejections per round, then brainstorm).
4. **OpenCode codes.** Run `opencode run -m opencode/deepseek-v4.1-flash-free <prompt>`: the OpenCode startup prompt in TEAM_RECOVERY.md section 5, plus any vetter feedback from a failed attempt.
5. **Claude vets the code.** Run
   `claude -p <prompt> --allowedTools "Read" "Grep" "Glob" "Bash(git diff:*)" "Bash(git status:*)" "Bash(.venv/Scripts/python.exe -m pytest:*)" "Bash(.venv/Scripts/python.exe scripts/team_score.py)"`.
   Prompt: read `git diff` and `git status`; check only files in the plan's "## Files" changed; run the plan's tests plus `tests/test_ai_bridge.py tests/test_team_score.py`; run `scripts/team_score.py`; end with `VERDICT: PASS` or `VERDICT: FAIL: <reason>`.
   FAIL: send the reason back to OpenCode (step 4), max 2 tries; then roll back: `git checkout -- <plan files>` and delete new untracked plan files, log it, and count the round as no progress.
   PASS: `git add` ONLY the plan's files plus `docs/agent_handoffs/TEAM_LOG.md` and NEXT_TASK.md, then `git commit -m "team: <first heading of NEXT_TASK.md>"`. Never `git add -A`. Never push. Never switch to main.
6. **Progress.** Run `scripts/team_score.py`. Progress = notus right or adrian right went up AND adrian misses_called_makes is 0. If adrian misses_called_makes goes above 0, log it as a regression and stop. If `goal_reached` is true, stop with GOAL_REACHED.
7. Delete `.team/STOP.md` and NEXT_TASK.md before the next round (they are logged and committed first).

**Brainstorm round:** ask each agent (Hermes, OpenCode, Claude, same commands) for up to 3 ideas to move the goal, each with why it is not a banned trial or looser cutoff. Append them to the log under `## Brainstorm <timestamp>`. Claude's prompt also asks it to mark any idea that breaks the Golden Rules as REJECTED. Then Hermes plans again with the brainstorm in its log context.

**Stop** on: GOAL_REACHED, SCOTT_GATE, CANNOT_REACH after a brainstorm, MaxNoProgress rounds in a row with no progress, a regression, an agent command failing or timing out (30 min per call), or MaxRounds. On stop: write `C:\Users\scott\Documents\Team_Loop_Recap_<yyyyMMdd_HHmm>.md` (why it stopped, rounds run, commits made, start and end score, open questions for Scott), append it to the log, commit the log, and `Start-Process notepad.exe <recap>`.

**-DryRun:** do every step except calling hermes/claude/opencode and committing: print each exact command it would run, run `scripts/team_score.py` for real, write to the log, and stop after round 1 with a recap.

No double quotes, backticks, or dollar signs inside prompt text passed to wsl. Pass Claude and OpenCode prompts as single arguments; build long prompts in here-strings.

## Tests to run before reporting
- `.\.venv\Scripts\python.exe -m pytest tests/test_team_score.py tests/test_ai_bridge.py -q`
- PowerShell parse check: `[System.Management.Automation.Language.Parser]::ParseFile` on team_loop.ps1 with 0 errors.
- `.\team_loop.ps1 -DryRun` completes and prints the commands.

Do not commit. Claude Code vets first.

---
## Vetter feedback, revision 2 (Claude Code, 2026-10-26 20:10) — VETTED to fix; edit only team_loop.ps1

Checked: tests 10 passed; team_score.py prints Notus 24/31/7/0 and Adrian 99/111/12/0; parse 0 errors; run_hermes.sh has LF endings; -DryRun completes. Fix these four in `team_loop.ps1` only:

1. **cmd.exe breaks OpenCode prompts.** `opencode` resolves to `opencode.cmd`, so `<`, `>`, `&`, `|`, `^`, `%` and newlines in an argument are parsed by cmd.exe. The Run-Code prompt contains `<the test files>`. Fix: for every OpenCode AND Claude call, write the full prompt to `.team/prompt_opencode.txt` / `.team/prompt_claude.txt` (UTF-8, no BOM) and pass only the one-line argument `Read .team/prompt_opencode.txt and follow it exactly.` (or the claude equivalent). Remove `<the test files>` from the text; say "the test files the plan lists".
2. **Stale NEXT_TASK.md / STOP.md are reused.** The dry run tried to commit "Task: build the team loop (relay)", which is this spec, not a Hermes plan. And after a CANNOT_REACH brainstorm, STOP.md is never removed, so the next pass sees it again. Fix: immediately BEFORE every Hermes plan call, if `NEXT_TASK.md` or `.team/STOP.md` exists, log its full text, then remove it (`git rm -q --cached` first if git tracks it, then delete the file). At loop start, move an existing NEXT_TASK.md to `.team/previous_NEXT_TASK.md` and log that.
3. **Heartbeat and stall alarm (Scott's requirement).** Keep `.team/STATUS.md` current:
   - Rewrite it at every step start and end, and every 60 seconds while an agent runs (replace the single `Wait-Job -Timeout` with a loop of 60-second waits).
   - Content: `Now: <Agent> <step> (round N)`, `Started: HH:mm:ss`, `Elapsed: m min`, `Last activity: HH:mm:ss`, `Branch`, `Last score`, `Updated: yyyy-MM-dd HH:mm:ss`.
   - Activity = the job produced new output (`$job.ChildJobs[0].Output.Count` grew) OR the text of `git status --porcelain` changed since the last check.
   - If there is no activity for 20 minutes: stop the job, write `STALLED: <Agent> <step> — no activity for 20 min` at the top of STATUS.md, and `Stop-Loop` with that reason.
   - The 30-minute hard timeout per call stays.
   - On any stop, STATUS.md becomes `STOPPED: <reason>` plus the recap path and time.
4. **Recap detail.** Add to the recap: the full text of `.team/STOP.md` if one triggered the stop, the first 1500 characters of the last Claude verdict, and the commits made this run (`git log --oneline <start hash>..HEAD`; record the start hash at loop start).

Then run: the parse check, `.\.venv\Scripts\python.exe -m pytest tests/test_team_score.py tests/test_ai_bridge.py -q`, and `.\team_loop.ps1 -DryRun`. The dry run must NOT mention "build the team loop", and `.team/STATUS.md` must exist afterwards showing STOPPED. Do not commit.
