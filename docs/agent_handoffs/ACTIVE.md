# Active Task

Updated: 2026-08-09 (videos old-link hang)

Branch: `cursor/videos-fast-list-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | videos-fast-list |
| **status** | `done` |
| **assigned_to** | cursor-agent |

## Decision

Videos nav (`/videos`) was slow because `/api/videos` ran per-video `COUNT(*)` on ~53M `detections`. Light list fixed the UI, but bare `/api/videos` (bookmarks, audits, cross-links) still hung. Default the list endpoint to light; opt into counts with `?full=1` or `GET /api/videos/<id>`.

## Changes

- `GET /api/videos` — **light by default** (fast; counts null); `?full=1` / `light=0` for full counts
- `GET /api/videos?light=1&sort=title` — explicit light (UI)
- `GET /api/videos/<id>` — full counts for one video
- `/videos` UI uses light list; optional **Load counts** per row

## Try

- `/videos`
- `/api/videos` (must return quickly)
- Film Tool: `/film/<filename>?game_id=…`

## Report

### Proven

- Bare `/api/videos` timed out at 25s on local DB (~53M detections) before default-light.
- Light list and `/videos` / Film deep links returned 200 quickly.

### Inferred

- Scott’s “old link doesn’t work” was the hanging bare `/api/videos` (or anything waiting on it).

### Unknown

- Whether denormalized counts / indexes are wanted later (schema gate).
