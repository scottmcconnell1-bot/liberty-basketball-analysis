# CLAUDE.md — Liberty Basketball Analysis

This file loads automatically each session. It is a **pointer**, not a replacement.
The authoritative rules live in `AGENT_PROTOCOL.md` and `AUTHORITY.md` — read them
when doing anything beyond a trivial lookup.

## Authority order (from AGENT_PROTOCOL.md)

1. Scott's current instruction
2. Repository files on the active branch
3. Git history and remote branch state
4. Test results and runtime logs
5. Source-of-truth docs
6. Agent analysis
7. Agent memory — **advisory only, never project truth**

## Repository Truth Preflight — REQUIRED

Run this **before any claim** about commits, branches, files, docs, tests, or repo state:

```bash
pwd
git remote -v
git branch --show-current
git fetch origin jason-5-may-updates
git status --short --branch
git rev-parse HEAD
git rev-parse origin/jason-5-may-updates
```

If local `HEAD` != `origin/jason-5-may-updates`, run `git pull --ff-only origin jason-5-may-updates`.

Required language when preflight has not run or fails:

- Preflight not run: `Not verified yet.`
- HEAD differs from origin: `Local clone is stale.`
- Fetch failed: `Unknown; remote fetch failed.`

Do **not** say `fabricated`, `false`, `not real`, or `does not exist` about repo state
before preflight has checked the remote branch.

## Reporting standard

Separate every report into:

- **Proven** — directly verified from files, git history, tests, logs, or runtime behavior
- **Inferred** — reasonable conclusion from evidence
- **Unknown** — not yet verified

Never present inferred information as proven.

## Verification safety — do NOT run without Scott's explicit approval

`git reset --hard` · `git checkout -- <path>` · `git clean` · `git stash` ·
`git stash pop` · forced checkout that overwrites local changes

If local changes block verification, report:
`Unknown; local changes block verification. Approval needed to use a clean clone, worktree, stash, reset, or other cleanup.`

Prefer: clean clone → separate worktree → non-destructive remote inspection → ask Scott.

## Requires Scott's approval (AUTHORITY.md)

- `schema.sql` changes — table structure, columns, types, constraints
- New tables or columns; API URL/endpoint/request/response design
- Terminology, feature scope, phase transitions
- Flipping a feature flag `False` → `True`
- UI/UX decisions; new frameworks or libraries
- Merging to `jason-5-may-updates`
- Breaking changes; deleting code or features

Emergency rules: if unsure whether something needs approval → **ask**.
If `schema.sql` needs to change → **stop**. If existing tests break → **stop**.
If a feature flag is `False` → don't implement that feature yet.

## Production safety

Benchmarks and doc updates must not change production behavior without Scott's approval.
Detector production values stay: `models/ball_detector.pt`, class `0`, `ball_confidence=0.25`.

## Project isolation

Liberty work stays isolated. Never mix in data, logs, status, or recommendations from
unrelated projects (trader_bot, Alpaca, market positions, etc.). Verify `pwd` and
`git remote -v` point at this repo before reporting; if not, say
`Unknown; wrong repository context.`

## Stage numbering

Read `docs/STAGE_INDEX.md` before naming, renaming, verifying, or reporting a stage.
Never reuse stage numbers — add a lettered stage (`3C`, `4A`) instead of rewriting history.
Stage 3B = Review UI. Stage 3C = Possessions and Canonical Clips Foundation.

## Memory rule

Do not add, edit, consolidate, or delete private agent memory during project work
unless Scott explicitly says `update memory`. Repository evidence beats memory.

## Agent roles and handoffs

- `ALPHA` = navigator, reviewer, scope controller (legacy alias: Codex)
- `OWL` = executor, verifier, poller worker (legacy aliases: Hermes, OWL/Hermes, Rex)

Labels: `OWL ACTION` → `OWL DONE` / `OWL NEEDS` → `ALPHA APPROVED`.
**A label alone is never a valid handoff** — every state change needs a human-readable
GitHub comment on the same issue. Completion comments must list files changed, exact
tests run and results, and the commit hash or an explicit `Not pushed yet`.

If GitHub commenting is unavailable, use the repo fallback: write the report to
`docs/agent_handoffs/ISSUE_<number>_<short_task>.md`, commit, push, and report the hash.

## Where to look

| Question | File |
| --- | --- |
| Full agent rules | `AGENT_PROTOCOL.md` |
| Who approves what | `AUTHORITY.md` |
| Stage numbering | `docs/STAGE_INDEX.md` |
| Current handoff / open bug | `docs/agent_handoffs/ACTIVE.md` |
| Work queue | `docs/agent_handoffs/QUEUE.md`, `docs/COMPLETION_PATH.md` |
| Product direction | `VISION.md`, `ROADMAP.md` |
| Decisions and history | `DECISION_LOG.md`, `WORKLOG.md` |

Update `WORKLOG.md` after every task.

## Repo structure

```
app.py           Flask app — registers blueprints
config.py        Feature flags and app settings
schema.sql       DB schema — DO NOT change without Scott approval
helpers.py       DB connection, init, AI runtime helpers
stats.py         Stats aggregation
blueprints/      ai.py (video/analysis/possessions), clips.py, core.py, ...
tests/           pytest suite
docs/            Project docs
```

## Local environment (Linux workstation, updated 2026-09-09)

**Read `docs/agent_handoffs/LOCAL_STANDUP_2026-09-09.md` first** — it is the full handoff for
this machine (setup, every fix made, verification log, Scott gates, next steps).

- Shell is **fish**: `VAR=x cmd` fails; use `env VAR=x cmd`. Venv activate: `source .venv/bin/activate.fish`.
- `.venv/` is Python **3.13.14** (uv-managed; system 3.14 is unsupported) with the CPU CV stack.
  Always run tests as `.venv/bin/python -m pytest tests/ -q` → **631 passed, 29 skipped**.
- Run the app with `/home/myaccount/LibertyData/run-liberty-local.sh` (gunicorn, **127.0.0.1:8080**).
  Do not use `python app.py` / `scripts/launch_liberty.py` here — they bind `0.0.0.0` and auth is a no-op.
- `.env` holds a real `SECRET_KEY`; `LIBERTY_UPLOAD_FOLDER=/home/myaccount/LibertyData/uploads`
  keeps media outside the repo. `.env` is loaded before `config.py` is imported (fixed 2026-09-09).
- `models/*.pt` are hydrated (byte-exact). `data/videos/Q1_snippet.mp4` is hydrated for CPU smoke runs
  (~3.5× realtime: 5 min of film ≈ 17 min).
- `docs/agent_handoffs/ACTIVE.md` describes Scott's **Windows** box; its paths do not apply here.
- No NVIDIA GPU. No Ollama installed (LLM notes use the heuristic fallback). No tesseract.
