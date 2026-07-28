# OWL Summary for Codex — What Happened and Why

**Date:** 2026-06-13
**From:** OWL (Hermes agent, independent auditor)
**To:** Codex (project lead)
**Purpose:** Explain what OWL did on the repo and why, so Codex understands the current state.

---

## What Happened

### The Problem
When OWL began working, the local clone at `/home/monk-admin/liberty-basketball-analysis` was on the `main` branch. OWL assumed `main` was the working branch and did all initial work there:
- Wrote an audit against the `main` branch code
- Created VISION.md, ROADMAP.md, DECISIONS.md, AUTHORITY.md, README.md (`main` versions)
- Created Codex onboarding and briefing docs
- Pushed 6 commits to `main`

**This was wrong.** The actual working branch is `jason-5-may-updates`, which is 215 commits ahead of `main`. It contains the real codebase: 11 Flask blueprints, 16 test files, Docker deployment, experiments, the full AI pipeline — everything.

The `main` branch was a stale snapshot from May 15. The project had been developed on `jason-5-may-updates` all along.

### The Fix
Once OWL identified the mistake (by comparing with Codex's Windows audit, which had the correct jason branch code), OWL:

1. **Fetched `jason-5-may-updates`** from the remote
2. **Switched to `jason-5-may-updates`** locally
3. **Created updated governance docs** that reflect the actual jason branch state:
   - `VISION.md` — now correctly describes the blueprint-based architecture, AI pipeline, tests, Docker, etc.
   - `AUTHORITY.md` — updated to reference `jason-5-may-updates` as the working branch
   - `docs/AUDIT_2026-06-13.md` — updated audit findings against the real codebase
   - `docs/CODEX_BRIEFING.md` — comprehensive briefing with correct branch, correct architecture, correct state
   - `docs/CODEX_ONBOARDING.md` — onboarding guide
4. **Pushed 3 new commits** to `jason-5-may-updates`:
   - `cd01015` — Add governance docs and Codex onboarding
   - `57b7ce7` — Update OWL audit for jason-5-may-updates branch reality
   - `80f4d81` — Add OWL summary for Codex explaining branch mistake and fix

### What This Means for Codex
- **Ignore the `main` branch.** It has 6 commits from OWL that were written against stale code.
- **All OWL docs are now on `jason-5-may-updates`.** Read them from there.
- The Codex briefing (`docs/CODEX_BRIEFING.md`) on jason is the authoritative starting point.
- The audit (`docs/AUDIT_2026-06-13.md`) on jason reflects the real codebase.

---

## Current Repo State

**Branch:** `jason-5-may-updates` (default, working branch)
**Commits from OWL:** 2 (cd01015, 57b7ce7)
**Files added by OWL on jason:**
- `VISION.md`
- `AUTHORITY.md`
- `docs/AUDIT_2026-06-13.md`
- `docs/CODEX_BRIEFING.md`
- `docs/CODEX_ONBOARDING.md`

**Files on jason that OWL did NOT touch (pre-existing):**
- `app.py` (blueprint-based Flask app)
- `config.py`, `helpers.py`, `schema.sql`
- `blueprints/` (11 modules)
- `templates/`, `static/`
- `tests/` (16 test files)
- `ai_analyzer.py`, `event_generator.py`, `film_analysis.py`, `tracker_assigner.py`
- `experiments/` (benchmark data, detector audits)
- `deploy/` (Docker, systemd, nginx)
- All existing docs in `docs/`

---

## How OWL and Codex Work Together

1. **Codex** works on the `jason-5-may-updates` branch (or feature branches from it)
2. **OWL** monitors the repo for issues with `[OWL ACTION]` prefix
3. When Codex needs something done on the Linux machine (push, merge, run tests, deploy), create a GitHub issue
4. When OWL needs Codex to do something, OWL creates an issue with `[CODEX ACTION]` prefix or comments on a PR
5. **Scott** reviews and approves all significant changes

---

## Known Issues (From Audit)

1. **Ball detection is non-functional** — 0/20 precision on v14 detector. Needs full rebuild.
2. **`.gitignore` already exists** on jason-5-may-updates — ignores film_analysis.db, uploads/, __pycache__/, .venv/, model weights, generated outputs, and experiments/. This audit item is resolved.
3. **Auth middleware disabled** — fine for local dev, must enable before network exposure
4. **Hardcoded secrets** in config.py — needs env var migration
5. **Dataset provenance gaps** — paths reference Linux machine, not portable

---

## Recommended First Steps for Codex

1. Read `docs/CODEX_BRIEFING.md` (on jason branch)
2. Read `VISION.md`, `AUTHORITY.md`, `docs/AUDIT_2026-06-13.md`
3. Verify the codebase: run tests, check app starts
4. Create `.gitignore`
5. Check if `game_id` type mismatch (TEXT vs INTEGER) exists on jason branch
6. Update `WORKLOG.md` with findings
7. Create a branch, push, create PR, tag OWL for review

---

## Lessons Learned

- **Always verify which branch is the working branch before starting work.**
- **Compare local state with remote state.** `git fetch` all branches first.
- **When an external agent (Codex on Windows) has a different view, reconcile immediately.**
- **Don't assume `main` is the default.** Check `git remote show origin` and `git ls-remote`.
