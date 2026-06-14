# Authority Boundaries — Liberty Basketball Analysis

## Who Does What

| Role | Identity | Responsibility |
|------|----------|----------------|
| **Scott** | Human coach, project owner | Final decision on everything. Approves phase transitions, feature changes, and anything on the "Requires Scott's Approval" list. |
| **Codex** | Project lead | Reads repo docs, proposes implementation plans, writes code, creates PRs, updates WORKLOG.md. Works autonomously within authority boundaries below. |
| **OWL (Hermes)** | GitHub executor + independent auditor | Executes git operations, manages repo, runs commands on the local machine. Provides outside-the-loop review when Scott requests it. |

## Codex Can Decide Autonomously

### Code & Implementation
- File structure, function signatures, variable naming, error handling, code style
- Implementation order within a task
- Internal refactoring that doesn't change behavior
- Bug fixes (typos, logic errors, crashes)
- Adding pip packages (flag for Scott's awareness)
- Test structure and test writing

### Documentation
- WORKLOG.md updates, inline comments, docstrings
- README updates (technical setup/usage)

### Git (via OWL)
- Branch naming, commit messages, when to commit

## Requires Scott's Approval

### Domain & Product
- **Data model changes:** Any change to `schema.sql` — table structure, column names, types, constraints
- **Terminology:** What things are called
- **Feature scope:** What a feature includes or excludes
- **Phase transitions:** Moving from one phase to the next
- **Feature flags:** Changing a flag from `False` to `True`

### Architecture
- New tables or columns
- API design: URL structure, endpoint names, request/response format
- UI/UX decisions: What pages look like, what's shown/hidden, user flows
- Technology choices: New frameworks, libraries, patterns

### Process
- Merging to main: Codex creates PRs, Scott merges
- Breaking changes: Anything that changes existing behavior
- Deleting code or features

## The Workflow

```
1. Codex reads VISION.md + ROADMAP.md + DECISIONS.md + AUDIT
2. Codex proposes a task plan (what files, what changes, what the diff will look like)
3. OWL posts the plan to Scott for approval (via Telegram)
4. Scott approves, adjusts, or rejects
5. Codex implements (writes code, creates branch, commits)
6. OWL pushes branch, creates PR
7. Scott reviews PR, requests changes or merges
8. Codex updates WORKLOG.md
9. Repeat
```

## Emergency Rules
- **If Codex is unsure whether something needs approval → ASK. Don't guess.**
- **If schema.sql needs to change → STOP. Get Scott's approval first.**
- **If existing tests break → STOP. Fix or ask.**
- **If a feature flag is False → Don't implement that feature yet.**

## How Codex Communicates With OWL

Codex and OWL coordinate through the GitHub repo:

1. **Codex needs OWL to do something** → Create a GitHub issue with `[OWL ACTION]` prefix
2. **OWL needs Codex to do something** → Create a GitHub issue with `[CODEX ACTION]` prefix or leave a PR review comment
3. **OWL monitors the repo** and picks up issues, pushes branches, creates PRs, runs commands on the machine

## Repo Structure

```
liberty-basketball-analysis/
├── app.py                  # Flask app — registers blueprints
├── config.py               # Feature flags and app settings
├── schema.sql              # Database schema — DO NOT change without approval
├── helpers.py              # DB connection, init, AI runtime helpers
├── film_analysis.py        # Enhanced analysis (minutes, shots, play recognition)
├── stats.py                # Stats aggregation
├── ai_analyzer.py          # YOLO detection on video frames
├── event_generator.py      # Converts detections → events
├── tracker_assigner.py     # Player tracking assignment
├── season_management.py    # Seasons CRUD
├── settings_store.py       # Runtime settings persistence
├── nfhs.py                 # NFHS integration
├── player_development.py   # Player development logic
├── requirements.txt        # Python deps
├── blueprints/             # Flask blueprints (11 modules)
│   ├── ai.py               # Video upload, AI analysis
│   ├── clips.py            # Clips, events, players
│   ├── core.py             # Index, schedule, videos, settings, dashboard
│   ├── games.py            # Games, sources, scheduled games, NFHS
│   ├── messaging.py        # Team messaging
│   ├── playbook.py         # Playbook management
│   ├── player_dev.py       # Player development clips, playlists
│   ├── practice.py         # Practices, notes, plan items
│   ├── scouting.py         # Scouting reports, opponent analysis
│   ├── stats.py            # Seasons, stats
│   ├── users.py            # User management
│   └── bulk_import.py      # Bulk data import
├── templates/              # HTML templates
├── static/                 # CSS/JS
├── tests/                  # 16 test files
├── docs/                   # Project docs
│   ├── AUDIT_2026-06-13.md      # OWL independent audit
│   ├── CODEX_ONBOARDING.md       # Codex onboarding guide
│   ├── CODEX_BRIEFING.md         # Comprehensive Codex briefing
│   ├── VERIFIED_PROJECT_FACTS.md # Verified technical facts
│   ├── DATASET_INVENTORY.md      # Dataset provenance
│   └── ...
├── experiments/            # Research/experiment scripts and data
├── deploy/                 # Deployment scripts and configs
├── VISION.md               # ← Start here
├── ROADMAP.md              # ← Then here
├── DECISIONS.md            # ← Then here
├── AUTHORITY.md            # ← This file
└── WORKLOG.md              # ← Update after every task
```
