# Active Task

Updated: 2026-08-09 (FastDraw play/set match MVP)

Branch: `cursor/fastdraw-play-match-ac1f`  
Base tip: `c4a0529` (coach-ledger / assisted-stat-sample merge)

## Meta

| Field | Value |
| --- | --- |
| **id** | fastdraw-play-match-mvp |
| **status** | `done` |
| **assigned_to** | cursor-agent |

## Scope delivered

- Match film possession movement against sticky FastDraw / playbook vector fingerprints
- Ranked suggestions only (confidence-as-rank) — **no auto-accept**
- Film Tool panel + `/film/<file>/plays?game_id=…` deep link
- JSON side cache `data/play_matches/{game_id}.json` (no schema.sql)

## Try

1. `/film/<stored_filename>/plays?game_id=<analysis_key>`
2. Or Film Tool → **Play / set suggestions** → Refresh matches
3. APIs: `GET /api/film/<game_id>/play-matches`, `?refresh=1`, `POST …/run`

## Docs

- `docs/PLAYBOOK_PLAY_MATCH.md` — method + MVP limits

## Report

### Proven

- Sticky choreography / play_steps fingerprints + formation/path ranker in `playbook_play_match.py`
- Film Tool panel + deep link + JSON side-file cache
- `tests/test_playbook_play_match.py` — 6 passed
- Auto-accept not wired; suggestions only

### Inferred

- Cloud-normalized formations are good enough to rank Rip-like vs Triangle-like synthetic fixtures
- Real film quality depends on sticky saves + possession windows + detection density

### Unknown

- Court homography quality for live game film vs half-court SVG
- Whether Scott has sticky choreography files for Rip / Triangle / Pitt 5 / 1-Game on disk yet
