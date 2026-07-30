# Full-Film Learning Panel

Fixed six-game evaluation for Liberty AI teaching. Scott’s success criteria (hard):

| Metric | Target |
| --- | --- |
| Final game score | **100%** exact (Liberty + opponent totals vs truth) |
| Points per player | **100%** exact for every player who should have points |
| Event precision | **≥ 90%** |
| Event recall | **≥ 90%** |

Do **not** use older 80% / 75% chat targets.

## Games (full film, no `--end-ms`)

| Name | film_id | analysis_key |
| --- | --- | --- |
| Idaho City | `hoopsalytics-idaho_city-2026-01-05` | `…__rerun_20260727_030810` |
| Harper | `hoopsalytics-harper_or-2025-12-05` | primary key |
| Burns | `hoopsalytics-burns_or-2025-12-06` | primary key |
| Nyssa | `hoopsalytics-nyssa-2025-12-04` | primary key |
| Melba | `hoopsalytics-melba-2025-12-09` | `…__rerun_20260723_022331` |
| Camas | `hoopsalytics-camas_county-2025-12-13` | `…__rerun_20260723_022404` |

If a preferred rerun key has zero events, the scorer falls back to the base key and **FLAGS** it.

## How to run

```bash
py -3.12 scripts/score_full_film_panel.py
```

Compare-only by default (minutes, not hours). `--regen` is reserved and does not regenerate unless you extend the script later.

Targets live in `data/hoopsalytics/full_film_panel_targets.json`.

## Outputs

- `data/hoopsalytics/full_film_panel_latest.json` — latest scorecard + gates
- `data/hoopsalytics/full_film_panel_history.jsonl` — one JSON object per run

## Reading PASS / FAIL

Console and JSON `evaluation.gates`:

- **`final_score_exact`** — PASS only if every panel game matches both team totals. If opponent AI points are unavailable, status is `partial` / Unknown and the gate **FAIL**s (never fake 100%).
- **`player_points_exact`** — PASS only if every truth scorer (points > 0) matches AI jersey points exactly, with no extra AI scorers. Incomplete jersey matching → `partial`/`unknown` and FAIL.
- **`event_precision_min` / `event_recall_min`** — mean precision/recall across panel games ≥ 0.90.
- **`overall_pass`** — all four gates PASS.

Exit code is **0** even when gates FAIL so the teach loop keeps running. Exit **1** only on hard script errors (missing compare script, missing DB, bad targets).

## Teach-loop hook

`scripts/hoops_teach_loop.py` runs the panel after a successful `teach_and_score`:

- Hoopsalytics: every teach (override with `LIBERTY_PANEL_EVERY_HOOPS`)
- HUDL: every 2 teaches by default (`LIBERTY_PANEL_EVERY_HUDL`)

Look for log lines starting with `PANEL …`.
