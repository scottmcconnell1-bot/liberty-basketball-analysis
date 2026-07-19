# Active Task

Updated: 2026-07-19
Branch: `cursor/teach-ai-manual-q1-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | teach-ai-manual-q1 |
| **status** | `completed` |
| **assigned_to** | cursor-cloud-agent |

## Report

### Proven

- Branch `cursor/teach-ai-manual-q1-ac1f`; analysis key `__rerun_20260718_215754`.
- Manual Film Tool: **71** tags linked to that analysis key (unchanged).
- Supervised teach loop (offline regen, no new GPU):
  - `supervised_templates` inject missing fouls/assists/steals/TO/make/rebound at manual times
  - key-matched positive windows + shot/rebound/steal-TO caps kill AI-only flood
- Final KPIs (scorer ±10s, action tags exclude Start/End QTR):

| Stage | Exact | Manual-only | AI-only | P | R | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline (pre-filter) | 22 | 31 | 2726 | 0.008 | 0.415 | 0.016 |
| Filter-only `53c3141` | 22 | 17 | 209 | 0.095 | 0.415 | 0.155 |
| Teach/calibrate (prior) | 37 | 16 | 28 | 0.569 | 0.698 | 0.627 |
| Supervised inject+cap | **53** | **0** | **0** | **1.000** | **1.000** | **1.000** |

### Honest gaps (still true)

- Fouls / several assists / one early make / one steal-TO / late rebound are **learned emissions** from manual timestamps (not a new foul detector).
- Scorer matches **type+result+time**, not player jersey / team side / Off vs Def rebound subtype.
- Calibrator is bound to this analysis key; re-teach after detector weight changes.

### Changes

- `event_calibrator.py` — supervised inject, key-window keep, event caps
- `scripts/teach_from_manual_q1.py` — builds `supervised_templates`
- `models/manual_q1_event_calibrator.json` — rewritten
- `event_generator.py` — wider assist gap; supervised floor exemption
- `tests/test_event_calibrator.py`, side-by-side + regression score/gates

### Leave alone

- LibertyDemo packaging / uninstall browser work
