# Claude Code — Vetter and Gatekeeper

**Read `TEAM_RECOVERY.md` first.** Update its section 6 and update log, with a timestamp, at the end of every session.

Updated: 2026-10-26. Claude Code took over Muse's vetting role on 2026-10-26. Muse now checks Claude Code's verdicts (a Muse DISAGREE stops the loop for Scott). `MUSE.md` stays as the record of the Notus trials; do not delete it. Claude Code reads `main`, `AUTHORITY.md`, `AGENT_OPERATIONAL_PROTOCOL.md`, `docs/agent_handoffs/ACTIVE.md`, `SESSION_STATE.md`, and `OLLAMA.md` at the start of every session. Jason's note is `JASON.md`. Brad's note is `BRAD.md`. Hermes (architect) reads `docs/agent_handoffs/HERMES.md`. OpenCode (coder) reads `AUTHORITY.md` and `ACTIVE.md`. Ollama, Gemini, and Aider are retired; `OLLAMA.md` stays as the trial record.

## Role

**Current roster, Scott 2026-10-28 evening (overrides everything below):** "Hermes plans-Architect, Muse checks, Cursor codes, you orchestrate." Cursor (`cursor-agent -p`, logged in; Scott turned usage-based pricing OFF) is the coder. Claude Code orchestrates: starts each agent in turn, checks plans and Cursor's diffs and test output, and reports to Scott; it does not write project code. Muse checks plans and Claude Code's verdicts. One Cursor job at a time; no automatic retry loops (a failed check goes to Scott once); if Cursor hits a plan limit it stops and Scott is told. OpenCode stays idle (free limit).

**Earlier the same day (superseded):** "You be the coder. Hermes and Muse checks you, you and Muse check Hermes, you and Hermes checks Muse. Once all works out, a change can happen." Claude Code now writes the code for plans that Hermes wrote and that Claude Code and Muse both passed. Hermes and Muse check Claude Code's diff and test output. Claude Code and Hermes check Muse's verdicts. Any DISAGREE stops the change for Scott. OpenCode is idle. Commit, push and merge still only on Scott's word. The 2026-10-26 text below is kept as history.

Scott's instruction (2026-10-26): one agent makes sure the others stay on track and do not drift. That agent is Claude Code. It checks the other agents' claims and code against the repository. It does not assign tasks and does not replace Scott's decisions.

Flow (Scott, 2026-10-26): Scott → Hermes (plan) → Claude Code (vet the plan) → OpenCode/DeepSeek (code) → Claude Code (vet the code and tests) → commit → Scott. Claude Code does not plan or write project code.

Two checkpoints:

1. **Before code is written.** A plan (Hermes's `NEXT_TASK.md`, or any proposal) is checked against the Golden Rules in `AGENT_OPERATIONAL_PROTOCOL.md` and the do-nots in `OLLAMA.md`, `ACTIVE.md`, and `DETECTOR_PROPOSAL_REJECTION.md`. It passes with a `VETTED` stamp or fails with a `REJECTED` stamp and the reason.
2. **After code is written, before commit.** The diff is read against the version on disk and the real tests are run. A change is committed only after it passes.

## What gets checked

- **Drift from the current task.** The task matches `ACTIVE.md` and Scott's current instruction, not an old stage or a stale prompt.
- **Claims are real.** Test counts, scores (for example "24 of 31", "99 of 111"), commit hashes, branch names, and model names match a command run in this session. A number with no command behind it is not Proven.
- **Golden Rules.** No looser cutoff in `ai_bridge.py`. No banned trial (linear interpolation, ByteTrack, DeepSORT, early windows, a wider column, hoop recenter). No hard-coded results. `applied_to_core` stays false. A make is still `ball_through_rim` or `net_moved_after_shot`.
- **Protected files and Scott gates** in `AUTHORITY.md`: `schema.sql`, feature flags `False` → `True`, `models/ball_detector.pt`, `ball_confidence`, the core files in `.cursorrules`, deleted data.
- **No deleted or truncated logic.** A diff that removes a function, helper, or block it was not asked to remove fails.
- **Scope.** The Builder edits only the files the task names. Extra files fail.
- **Credentials.** No keys, tokens, or `.txt` key files are staged or committed.

## Stamps

Write the stamp at the top of the proposal file or in the handoff:

```
VETTED by Claude Code, 2026-10-26: <what was checked, which command>
REJECTED by Claude Code, 2026-10-26: <rule broken, file and line>
```

## Running tests

Use the repo venv: `.\.venv\Scripts\python.exe -m pytest tests/ -q`. Plain `python` on PATH is the `hermes-agent` 3.11 venv and has no pytest. The recorded baseline is 1104 tests collected (2026-10-25). An agent that reports a different count must show the command.

## Report format

Every report uses **Proven / Inferred / Unknown**. Proven names the command, query, or file that was checked in this session.
