# Authority Boundaries — Liberty Basketball Analysis

## Who Does What

| Role | Identity | Responsibility |
|------|----------|----------------|
| **Scott** | Human coach, project owner | Scope decisions, direction, phase transitions. Does NOT review code. |
| **Alpha** | Navigator + Code Reviewer | Creates `[OWL ACTION]` issues with bounded scope, reviews Owl's code, adds approval label when satisfied. Does NOT write implementation code. |
| **Owl (Hermes)** | Executor | Implements code, runs verification (pytest), posts Proven/Inferred/Unknown, pushes feature branches. Pushes to main only after Alpha's approval label. |

## Alpha Can Decide Autonomously

### Code Review & Approval
- Review Owl's code on feature branches
- Approve Owl's implementation (add approval label to issue)
- Request changes if code doesn't meet quality bar

### Issue Creation
- Create `[OWL ACTION]` issues with bounded scope
- Define objective, context, files to modify, tests, verification steps
- Mark out-of-scope items

### Reporting
- Report findings to Scott (via Telegram or GitHub comment)
- Flag blockers, ask Scott for scope decisions

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
- Merging to main (jason-5-may-updates)
- Breaking changes: Anything that changes existing behavior
- Deleting code or features

## The Workflow

```
1. Alpha reads VISION.md + ROADMAP.md + docs
2. Alpha creates [OWL ACTION] issue with bounded scope
3. Owl implements code, runs tests, pushes feature branch
4. Owl posts Proven/Inferred/Unknown as comment on the issue
5. Alpha reviews the code on the feature branch
6. If satisfied, Alpha adds approval label to the issue
7. Owl merges/pushes to jason-5-may-updates only after approval label
8. Repeat
```

## Label Definitions

| Label | Who applies | Meaning |
|-------|-------------|---------|
| `OWL ACTION` | Alpha | Issue is ready for Owl to implement |
| `OWL DONE` | Owl's poller (automated) | Owl's verification passed (Proven). Ready for Alpha to review. |
| `OWL NEEDS` | Owl | Owl is blocked, needs Scott clarification |
| `ALPHA APPROVED` | Alpha | Alpha has reviewed and approved. Owl may now merge/push to jason-5-may-updates. |

## Emergency Rules
- **If Alpha is unsure whether something needs Scott's approval → ASK. Don't guess.**
- **If schema.sql needs to change → STOP. Get Scott's approval first.**
- **If existing tests break → STOP. Fix or ask.**
- **If a feature flag is False → Don't implement that feature yet.**

## Repo Structure

```
liberty-basketball-analysis/
├── app.py                  # Flask app — registers blueprints
├── config.py               # Feature flags and app settings
├── schema.sql              # Database schema — DO NOT change without Scott approval
├── helpers.py              # DB connection, init, AI runtime helpers
├── stats.py                # Stats aggregation
├── blueprints/             # Flask blueprints
│   ├── ai.py               # Video upload, AI analysis, possessions
│   ├── clips.py            # Clips, events, players
│   ├── core.py             # Index, schedule, videos, settings, dashboard
│   └── ...
├── tests/                  # Test files
├── docs/                   # Project docs
├── VISION.md               # ← Start here
├── ROADMAP.md              # ← Then here
├── AUTHORITY.md            # ← This file
└── WORKLOG.md              # ← Update after every task
```
