# Active Task

Updated: 2026-08-09 (ops: stale Flask + login)

Branch: `jason-5-may-updates` @ `c4a0529`  
Current working tip for Scott: coach-ledger unified tip (review + stat-book + sticky/assisted sample).

## Meta

| Field | Value |
| --- | --- |
| **id** | ops-stale-flask-login |
| **status** | `done` |
| **assigned_to** | cursor-agent |

## Included on this tip

- Videos light-list + Review button
- Coach-ledger foundation (auto-accept off + confirmed-box schema)
- Review workspace MVP — Accept/Correct/Reject in Film Tool
- Stat-book MVP — spiral scorebook extract/confirm
- Sticky choreography / assisted stating SAMPLE
- FastDraw / highlight / Active-Archive tabs: **not** on this tip yet (separate branches)

## Try (after hard refresh)

1. `http://127.0.0.1:8080/videos` — Review button; light list
2. `http://127.0.0.1:8080/stat-books` — must be 200 (proves new code)
3. `http://127.0.0.1:8080/film/assisted-stat-sample`
4. Staff login: `/login` with email (not username)
5. Coach: `/coach` with `.env` `LIBERTY_COACH_PASSWORD`

## Ops report (2026-08-09 night)

### Proven

- Stale Flask (started 6:23 PM) was older than tip merge (7:43 PM) → `/stat-books` 404 and missing UI.
- Killed launchers + app.py; restarted one clean `app.py` on :8080 from tip.
- Staff login works with email `smcconnell@legacycharterschool.net` (DB password matches known Hoops password).
- Local fix: one bad Windows-1252 byte in `blueprints/core.py` docstring blocked UTF-8 import (uncommitted 1-line fix).
- `TEACH_LOOP_PAUSED` left in place; teach loop not restarted.

### Inferred

- Scott signing in with a username (not email) would always fail — form field is `email`.
- “No UI changes” was stale process, not wrong branch tip (jason already at coach-ledger merge).

### Unknown

- Whether Active/Archive videos UI was expected tonight (not on `c4a0529`; fastdraw/highlights still separate).
