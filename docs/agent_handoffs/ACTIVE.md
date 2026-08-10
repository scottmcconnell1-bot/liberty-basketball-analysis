# Active Task

Updated: 2026-08-09

Branch: `cursor/highlight-clips-ac1f`  
Base: `c4a0529` (`jason-5-may-updates` / coach-ledger tip)

## Meta

| Field | Value |
| --- | --- |
| **id** | highlight-clips-mvp |
| **status** | `done` |
| **assigned_to** | cursor-agent |

## Goal

Highlight clip generation from the **reviewed event ledger** — filter by jersey / event type, list moments, save clip rows + optional ffmpeg cuts (else seek/export list).

## Try

1. `/highlights` — pick game → filter jersey and/or event type → List moments
2. Select moments → **Generate clips** (saves PD/canonical clips; starts ffmpeg trims when available) or **Download clip list**
3. Empty game with no accepted/corrected events shows Review workspace instruction
4. `/api/highlights/games`, `/api/highlights/moments`, `POST /api/highlights/generate`

## Report

### Proven

- Source of truth: `events.review_status IN ('accepted','corrected')` via `highlight_clips.py` + `_trusted_event_review_clause`.
- Pending AI events excluded from moments and generate (returned in `missing_event_ids`).
- UI + APIs in `blueprints/clips.py`; nav link under Film & Stats.
- Generate reuses `player_development.create_clip` (canonical `clips` + `player_development_clips`) and `video_trim.start_trim_job` when ffmpeg + video exist.
- Seek links use Film Tool `?t=` / `game_id=` pattern.

### Inferred

- Jersey filter matches bare numbers and labels containing the number token; roster jersey_number column not required for MVP.

### Unknown

- Whether Scott wants batch zip download of finished ffmpeg outputs in a follow-up (jobs currently pollable via `/api/videos/trim/<job_id>`).
