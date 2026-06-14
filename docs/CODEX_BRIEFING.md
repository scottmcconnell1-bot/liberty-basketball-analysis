# Codex Briefing — Liberty Basketball Analysis

**Date:** 2026-06-13
**From:** OWL (independent auditor, Hermes agent)
**To:** Codex (project lead)

---

## What This Document Is

This is your complete onboarding package. Read it start to finish before doing anything. Everything about the project, the people, the codebase, and how we work together is here.

**IMPORTANT:** The primary working branch is `jason-5-may-updates` — NOT `main`. The `main` branch is stale. All development happens on `jason-5-may-updates`.

---

## 1. The Project

**Liberty Basketball Analysis** is a basketball film and analytics system for a real coach (Scott McConnell) to use in-season. It manages seasons, schedules, games, film sources, stats, player development, and practice cut-ups. It also includes AI-powered video analysis using YOLO for object detection.

**Tech stack:** Flask + Blueprints, SQLite, vanilla HTML/JS, Python 3, YOLO (Ultralytics)

**Repo:** https://github.com/scottmcconnell1-bot/liberty-basketball-analysis
**Working branch:** `jason-5-may-updates` (default branch, 215 commits ahead of main)

---

## 2. The People and Their Roles

| Role | Who | What They Do |
|------|-----|--------------|
| **Scott McConnell** | Human coach, product owner | Final decision on everything. Nothing goes to production without Scott's OK. |
| **Codex** | Project lead (you) | Day-to-day architecture, implementation, code review. Propose plans, write code, create branches, update WORKLOG.md. |
| **OWL (Hermes)** | GitHub executor + auditor | Runs git operations on the local machine, deploys, automates. Provides outside-the-loop review. |

**Key principle:** Authority flows from repo documents, not from who has access.

---

## 3. Read These Files In This Order

1. **`VISION.md`** — What this project is, core principles, current state
2. **`docs/IMPLEMENTATION_PLAN.md`** — Detailed phase status (says P1-P7 complete)
3. **`DECISIONS.md`** — Decision log
4. **`AUTHORITY.md`** — Who decides what, workflow, repo structure
5. **`docs/AUDIT_2026-06-13.md`** — OWL's independent audit (written against main branch; some findings may be stale for jason)
6. **`docs/VERIFIED_PROJECT_FACTS.md`** — Verified technical facts about the project
7. **`docs/DATASET_INVENTORY.md`** — Dataset provenance documentation
8. **`WORKLOG.md`** — Recent development activity

---

## 4. Current State (jason-5-may-updates branch)

The codebase is significantly more mature than what the old main branch showed:

- **Architecture:** Flask + 11 Blueprints, SQLite, server-rendered templates
- **Blueprints:** core, games, clips, stats, practice, player_dev, ai, playbook, messaging, users, scouting, bulk_import
- **Entry point:** `app.py` (registers blueprints, 127 lines)
- **Database:** `film_analysis.db` with schema in `schema.sql`
- **AI pipeline:** `ai_analyzer.py` (YOLO detection) → `event_generator.py` (events) → `film_analysis.py` (enhanced analysis)
- **Tests:** 16 test files under `tests/`
- **Deployment:** Docker, docker-compose, systemd service, nginx config
- **Experiments:** `experiments/` directory with benchmark data, detector audits
- **Docs:** Extensive docs in `docs/` including verified facts, dataset inventory, protocol test logs

**Phase status (per IMPLEMENTATION_PLAN.md):**
- P1-P7: All marked complete
- Dashboard: Complete (team cards, schedule, rankings, photos)
- AI/ball detection: Implemented but audit shows quality issues (see below)

---

## 5. Known Issues and Technical Debt

### Critical
1. **Ball detection quality is poor** — `experiments/detector_audit_top20/AUDIT_RESULTS.md` shows v14 detector scored 0/20 (0% precision). The detector needs a full rebuild with proper training data, validation methodology, and benchmark evaluation.
2. **No `.gitignore`** on the jason branch — `film_analysis.db`, `uploads/`, `__pycache__/`, `*.pyc`, `.venv/` could be committed.
3. **Auth middleware is disabled** — `app.py` line 97: `pass  # No auth enforced yet`. This is fine for local dev but must be enabled before any network exposure.

### Important
4. **Hardcoded secrets in config.py** — Dev secret and VAPID private key are hardcoded. Needs environment variable migration.
5. **Dataset provenance gaps** — `docs/DATASET_INVENTORY.md` references datasets on the Linux machine (`/home/monk-admin/...`) that don't exist on Windows. Need to document what's actually available locally.
6. **requirements.txt is bloated** — Contains CUDA/torch/ultralytics deps. Consider splitting into web vs CV requirements.

### From OWL Audit (some may be stale for jason branch)
7. **`game_id` type inconsistency** — Check if `events.game_id` (TEXT) vs `games.id` (INTEGER) is still an issue on this branch.
8. **Legacy files** — `tracker_assigner.py`, `ai_analyzer.py`, `event_generator.py` in root may need to be moved to `src/` or `legacy/`.

---

## 6. What You Can Decide Autonomously

- File structure, function signatures, variable naming, code style
- Implementation order within a task
- Internal refactoring (doesn't change behavior)
- Bug fixes (typos, logic errors, crashes)
- Adding pip packages (flag for Scott's awareness)
- WORKLOG.md updates, inline comments, docstrings
- Branch naming, commit messages, when to commit
- Test writing and test structure

## 7. What Requires Scott's Approval

- **Any change to `schema.sql`** — table structure, column names, types, constraints
- **Terminology** — what things are called
- **Feature scope** — what a feature includes/excludes
- **Phase transitions** — moving from one phase to the next
- **Feature flags** — changing a flag from `False` to `True`
- **New tables or columns**
- **API design** — URL structure, endpoint names
- **UI/UX decisions** — page layouts, user flows
- **Technology choices** — new frameworks, libraries
- **Merging to jason-5-may-updates** — create PRs, Scott merges
- **Breaking changes** — anything that changes existing behavior
- **Deleting code or features**

### Emergency Rules
- **If unsure → ASK Scott. Don't guess.**
- **If schema.sql needs to change → STOP. Get Scott's approval first.**
- **If existing tests break → STOP. Fix or ask.**
- **If a feature flag is False → Don't implement that feature yet.**

---

## 8. How to Communicate With OWL (Hermes)

You and OWL work together through the GitHub repo:

### When You Need OWL to Do Something
Create a GitHub issue with `[OWL ACTION]` prefix:
```
[OWL ACTION] <short description>

<detailed explanation>

Context: <phase/task reference>
```

OWL monitors the repo, picks up issues, pushes branches, creates PRs, runs commands on the Linux machine.

### When OWL Needs You to Do Something
OWL will create issues or PR review comments with `[CODEX ACTION]` prefix.

### Branch Naming
- `fix/<description>` — bug fixes
- `feature/<description>` — new features
- `audit/<description>` — audit-related fixes
- Always branch from `jason-5-may-updates`

### Commit Format
```
<type>: <short description>

Context: <phase/task reference>
```

Types: `fix:`, `feat:`, `refactor:`, `docs:`, `chore:`

---

## 9. Key Constraints (Non-Negotiable)

1. `schema.sql` is the single source of truth for the database
2. `events`, `analysis_runs`, `detections` tables must not be broken
3. Every feature is behind a feature flag
4. Small, reviewable steps — nothing merged without approval
5. SQLite only — no other database
6. Vanilla HTML/JS — no frontend frameworks
7. Single coach, single machine — not a SaaS
8. Any feature must be usable in under 5 minutes on a game night
9. **Evidence over assumptions** — verify everything, report proven/inferred/unknown separately

---

## 10. How to Run the App

```bash
cd /path/to/liberty-basketball-analysis
python3 app.py
# → http://localhost:5000/
```

---

## 11. Your First Tasks

1. **Read all documents** listed in Section 3
2. **Verify the codebase state** — run the tests, check the app starts, confirm the audit findings against the actual jason branch code
3. **Create `.gitignore`** — add `film_analysis.db`, `uploads/`, `__pycache__/`, `*.pyc`, `.venv/`
4. **Check `game_id` type consistency** — verify if events.game_id (TEXT) vs games.id (INTEGER) is still an issue
5. **Update WORKLOG.md** with your findings
6. **Push to a branch**, create a PR, tag OWL for review

---

## Questions?

Create a GitHub issue with `[QUESTION]` prefix and OWL will route it to Scott.
