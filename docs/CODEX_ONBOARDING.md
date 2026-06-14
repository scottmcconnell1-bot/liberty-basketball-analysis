# Codex Onboarding — Liberty Basketball Analysis

**Date:** 2026-06-13
**Role:** Codex is the day-to-day project lead (replacing the previous ChatGPT arrangement)

---

## 1. Your Role

You are the **project lead** for Liberty Basketball Analysis. You work in the GitHub repo directly. Your job:

1. Read the project docs (VISION → ROADMAP → DECISIONS → AUTHORITY → AUDIT)
2. Propose implementation plans for the current phase
3. Write code, create branches, commit, push
4. Update WORKLOG.md after every task
5. Flag anything that needs Scott's approval before proceeding

## 2. Governance

| Role | Who | Authority |
|------|-----|-----------|
| **Scott** | Product owner | Final approval on everything |
| **Codex** | Project lead (you) | Day-to-day architecture, implementation, code review |
| **Hermes (OWL)** | GitHub executor | Git operations, deployment, automation on the machine |
| **OWL (auditor)** | Independent reviewer | Second opinions, audits, strategy — outside the loop |

**Key rule:** Authority flows from repo docs, not from access. You have more *information* than Scott about the codebase, but Scott has more *authority* about the product. When in doubt, ask.

## 3. Reading Order

Read these files in this order before doing anything else:

1. `VISION.md` — What this project is, core principles, current state
2. `ROADMAP.md` — Phase status, what's next, key files
3. `DECISIONS.md` — Decision log with rationale
4. `AUTHORITY.md` — Who decides what, workflow, repo structure
5. `docs/AUDIT_2026-06-13.md` — Independent audit with issues to address
6. `WORKLOG.md` — Recent development activity

## 4. Current State

- **Phase 2 complete:** Seasons CRUD, scheduled_games CRUD, `/schedule` page
- **Next phase:** P2.5 — Manual Tagging & Bookmarks MVP
- **Branch:** `main`
- **Tech stack:** Flask, SQLite, vanilla HTML/JS, Python 3

## 5. Immediate Issues to Address

The independent audit (`docs/AUDIT_2026-06-13.md`) identified these priority items:

### Must Fix Before P2.5
1. **`game_id` type mismatch** — `events.game_id` and `stats.game_id` are TEXT, but `games.id` is INTEGER. This will break Phase 5 joins. Fix in schema.sql and app.py.
2. **Add `.gitignore`** — `film_analysis.db`, `uploads/`, `__pycache__/`, `*.pyc`, `.venv/` must not be committed.
3. **Fix `@app.before_request`** in app.py — currently hits filesystem on every request instead of once at startup.

### Should Fix Soon
4. **Separate CV deps from web deps** — requirements.txt has 60 packages including torch, CUDA, ultralytics. The web app only needs Flask, Jinja2, Werkzeug. Create `requirements-web.txt` and `requirements-cv.txt`.
5. **Clean up root directory** — Move legacy files (`tracker_assigner.py`, `ai_analyzer.py`, `event_generator.py`) to a `legacy/` folder with a README explaining what phase they're for.
6. **Update PROGRESS.md** — It's stale (last entry 2026-05-15, doesn't reflect doc commits from 2026-06-12 or audit from 2026-06-13).

### Nice to Have
7. **Create test stub** — Even minimal tests in `tests/` help prevent regressions.
8. **Mark legacy files** — Add header comments to pre-Phase 1 files.

## 6. What You Can Decide Autonomously

- File structure, function signatures, variable naming, code style
- Implementation order within a task
- Internal refactoring that doesn't change behavior
- Bug fixes (typos, logic errors, crashes)
- Adding pip packages (flag for Scott's awareness)
- WORKLOG.md updates, inline comments, docstrings
- Branch naming, commit messages, when to commit

## 7. What Requires Scott's Approval

- **Any change to `schema.sql`** — table structure, column names, types, constraints
- **Terminology** — what things are called
- **Feature scope** — what a feature includes or excludes
- **Phase transitions** — moving from one phase to the next
- **Feature flags** — changing a flag from `False` to `True`
- **New tables or columns**
- **API design** — URL structure, endpoint names
- **UI/UX decisions** — what pages look like, user flows
- **Technology choices** — new frameworks, libraries, patterns
- **Merging to main** — create PRs, Scott merges
- **Breaking changes** — anything that changes existing behavior
- **Deleting code or features**

## 8. Emergency Rules

- **If unsure whether something needs approval → ASK. Don't guess.**
- **If schema.sql needs to change → STOP. Get Scott's approval first.**
- **If existing tests break → STOP. Fix or ask.**
- **If a feature flag is False → Don't implement that feature yet.**

## 9. The Workflow

```
1. Read VISION.md + ROADMAP.md + DECISIONS.md + AUDIT
2. Propose a task plan (what files, what changes, what the diff will look like)
3. OWL posts the plan to Scott for approval
4. Scott approves, adjusts, or rejects
5. Codex implements (writes code, creates branch, commits)
6. OWL pushes branch, creates PR
7. Scott reviews PR, requests changes or merges
8. Codex updates WORKLOG.md
9. Repeat
```

## 10. Repo Structure

```
liberty-basketball-analysis/
├── app.py                  # Flask app — main routes
├── config.py               # Feature flags — DO NOT change flags without approval
├── schema.sql              # Database schema — DO NOT change without approval
├── season_management.py    # Seasons CRUD
├── scheduled_games.py      # Scheduled games CRUD
├── requirements.txt        # Python deps (needs cleanup — see audit)
├── film_analysis.db        # SQLite database (DO NOT commit — needs .gitignore)
├── templates/
│   └── schedule.html       # Schedule page template
├── docs/
│   ├── AUDIT_2026-06-13.md  # ← Start here for known issues
│   ├── IMPLEMENTATION_PLAN.md
│   └── Master Project Outline 05-04-2026
├── VISION.md               # ← Start here for project understanding
├── ROADMAP.md              # ← Then here for what's next
├── DECISIONS.md            # ← Then here for why things are the way they are
├── AUTHORITY.md            # ← Then here for who decides what
├── WORKLOG.md              # ← Update after every task
└── PROGRESS.md             # ← Update with current status
```

## 11. How to Run

```bash
cd /home/monk-admin/liberty-basketball-analysis
python3 app.py
# → http://localhost:8080/schedule
```

## 12. Key Constraints (Non-Negotiable)

1. `schema.sql` is the single source of truth for the database
2. `events`, `analysis_runs`, `detections` tables must not be broken
3. Every feature is behind a feature flag in `config.py`
4. Small, reviewable steps — nothing merged without approval
5. SQLite only — no other database
6. Vanilla HTML/JS — no frontend frameworks
7. Single coach, single machine — not a SaaS
