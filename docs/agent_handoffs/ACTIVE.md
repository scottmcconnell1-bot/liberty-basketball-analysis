# Active Task

Updated: 2026-08-30 (work PC sync + early lookaround v2)

Branch: `cursor/film-tool-review-layout-ac1f`  
Base: `jason-5-may-updates`  
HEAD: early lookaround v2 on this branch

## Meta

| Field | Value |
| --- | --- |
| **id** | adrian-accuracy-quality |
| **status** | `in_progress` |
| **assigned_to** | cursor-agent |
| **scope** | **Adrian JrHigh only** until Scott says accurate |
| **game_id** | `jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334` |

## Why

Make the Adrian film ledger accurate before other games. Scott reviews on Film Tool at home and work.

## Done (Proven)

- Branch checked out on work PC; tracks `origin/cursor/film-tool-review-layout-ac1f`
- Overlay fix + steal labels + quality filters present in tree (`ensureFilmToolOverlaysClosed`, tip_off, drop rebound-before-steal)
- **2026-08-30 work PC:** `adrian_jersey_lookaround_v2` — early game (&lt;120s): OCR floor 0.35, single sample OK if conf≥0.55, extra 30‑min lookaround window. Unit tests in `tests/test_adrian_identity_lookaround.py`

## Blocked on this machine

- **No `film_analysis.db`** on work PC (dual-machine: DB is local-only). Cannot run:
  - `python scripts/refine_adrian_events.py`
  - `python scripts/apply_adrian_jersey_lookaround.py`
- Work PC has `python` 3.14; no `py -3.12` runtime installed

## Try (home or any machine with DB)

1. `git pull` this branch
2. `python scripts/refine_adrian_events.py`
3. `python scripts/apply_adrian_jersey_lookaround.py`
4. Restart Flask (home: Flask-only; do not kill teach/launcher) → hard-refresh Film Tool
5. `?game_id=jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334`
6. Ledger: first play ~3.3s = tip_off; ~13s = steal (not rebound @ ~11s); no black overlay on load
7. Early steals/tips should show more scorebook names after lookaround v2 (not only tracker IDs)

## Still open

- [ ] Scott confirms tip_off / steal / no overlay on Film Tool
- [ ] Re-run refine + lookaround where DB exists; report matched/unresolved counts
- [ ] NFHS film timing spot-check (sync offset currently 0)
- [ ] Remaining unresolved jerseys after v2

## Do not

- Change `schema.sql` / flip feature flags / ball detector settings without Scott
- Unpause teach loop / raise auto-accept
- Run Adrian quality on other games yet

## Report

### Proven

- Work PC on `cursor/film-tool-review-layout-ac1f` (synced)
- Lookaround v2 code + unit tests (no live DB on this machine)
- Dual-machine: git syncs code; `film_analysis.db` / uploads stay local (`docs/DUAL_MACHINE.md`)

### Inferred

- Early sparse OCR is why tip/steal rows still show tracker IDs; v2 should recover unique jerseys when the same track OCRs later or with slightly weaker confidence

### Unknown

- Matched/unresolved counts after re-apply on home DB
- Whether ByteTrack IDs for the ~13s steal persist long enough for the 30‑min window to help
