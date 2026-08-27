# Active Task

Updated: 2026-08-26 (Adrian timing vs film — quality v2 spread)

Branch: `cursor/film-tool-review-layout-ac1f`  
Base: `jason-5-may-updates`

## Meta

| Field | Value |
| --- | --- |
| **id** | adrian-accuracy-quality |
| **status** | `in_progress` (team PTS match; timestamps spread; jersey/team still wrong) |
| **assigned_to** | cursor-agent |
| **scope** | **Adrian JrHigh only** until Scott says accurate |

## Why

Blind program promote left ~13k accepted events / ~5k AI PTS vs scorebook ~77. CV firehose + tracker IDs ≠ jerseys. Quality v1 capped counts but kept early high-confidence noise (first ~2 min), same-ms pileups (miss+reb+block), and no team/player labels.

## Done (Proven)

- `adrian_quality.py` v2 — temporal dedupe + **same-timestamp collapse** + **time-spread caps** (not top-confidence-only) + scorebook make/FT caps
- After v2 refine: **team PTS 77**; accepted spread across ~0–58 min (was ~114 under 2:00 / 24 after → now **36 under 2:00 / 179 after**); no 3-way same-ms pileups
- Frame match: NFHS clean vs archived screencapture body clocks **~aligned** (median offset ~1s); offset file `data/film_sync/…json` = 0; Film Tool sync bar for manual tip calibration if needed
- Clip review loop, dock, Accept/Reject speed, coach exit, 30‑min Liberty watchdog (prior)

## Try

1. Hard-refresh Film Tool → Adrian NFHS clean → **Build / refine Adrian ledger** (if not already on v2)
2. **Show ledger plays** — rows should land across the game, not only tip-off
3. Still expect tracker IDs (`#2`) not jerseys; almost no team label — identity is next
4. Film sync bar under Build: leave at 0 unless tip is clearly off

## Next (still Adrian only)

1. Jersey/track ID + team (Liberty vs Adrian) on ledger rows
2. Spot-check a mid-game make/miss on film after v2 spread
3. Only then expand quality path beyond Adrian

## Do not

- Unpause teach loop (`TEACH_LOOP_PAUSED`)
- Flip `auto_accept_event_confidence`
- Run quality/auto-ledger on other games yet
