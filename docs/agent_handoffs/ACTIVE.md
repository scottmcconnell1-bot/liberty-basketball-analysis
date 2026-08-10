# Active Task

Updated: 2026-08-09 (videos archive)

Branch: `cursor/videos-archive-ac1f`  
Base: `cursor/coach-ledger-ac1f` / `jason-5-may-updates` @ `c4a0529`

## Meta

| Field | Value |
| --- | --- |
| **id** | videos-archive |
| **status** | `done` |
| **assigned_to** | cursor-agent |

## Goal

Organize `/videos` light list into **Active** vs **Archive** so Scott is not confused by a long mixed game list.

## Try

1. `/videos` — Active list (default), A–Z, badges Active (N) | Archive (M)
2. Row **Archive** → game leaves Active; open Archive tab (`/videos?view=archive`) to see it
3. Row **Unarchive** → back on Active
4. Film Tool / Review deep links still open archived games

## Report

### Proven

- Runtime `ALTER TABLE videos ADD COLUMN archived INTEGER NOT NULL DEFAULT 0` (no `schema.sql` change).
- `GET /api/videos` defaults to `archived=0`; `archived=1` / `archived=all` supported; light list unchanged (no N× detection counts).
- `POST /api/videos/<id>/archive` and `/unarchive`; `GET /api/videos/archive-counts`.
- Tests: `test_api_videos_archive_filter_and_toggle` in `tests/test_api.py`.

### Inferred

- Defaulting bare `/api/videos` to active-only is desirable for the library UI; callers that need every row can pass `archived=all`.

### Unknown

- Whether Scott later wants archive to also hide games from other surfaces (status, assistant workflow).
