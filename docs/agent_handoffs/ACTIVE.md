# Active Task

Updated: 2026-08-09 (videos fast list)

Branch: `cursor/videos-fast-list-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | videos-fast-list |
| **status** | `done` |
| **assigned_to** | cursor-agent |

## Decision

Videos nav (`/videos`) was slow because `/api/videos` ran per-video `COUNT(*)` on ~53M `detections` (no useful index) for every row, and polled every 10s. List-first with light metadata is the fix; Film Tool already loads one video.

## Changes

- `GET /api/videos?light=1&sort=title` — skip detection/event counts; sort A–Z by title
- `GET /api/videos/<id>` — full counts for one video
- `/videos` UI uses light list; optional **Load counts** per row; poll only while runs are active

## Try

- `/videos`
- Film Tool deep links unchanged: `/film/<filename>?game_id=…`

## Report

### Proven

- Local DB: 54 videos, ~52.8M detections, ~618k events; full `COUNT(*)` on detections ~45s table-wide.
- Light list skips those counts; detail endpoint loads one video’s counts.

### Inferred

- Prior UI felt multi‑minute / hang because list × N counts + 10s refresh.

### Unknown

- Whether denormalized counts on `analysis_runs` or detections indexes are wanted later (schema gate).
