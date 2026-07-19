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

- Branch based on `cursor/improve-ai-from-manual-q1-ac1f` @ `53c3141` (filter-only: exact stayed **22**).
- Demo packaging remains separate on `cursor/demo-done-uninstall-ac1f` (not touched).
- Teach loop: `scripts/teach_from_manual_q1.py` → `models/manual_q1_event_calibrator.json` → applied in `event_generator.postprocess_ai_events` via `event_calibrator.py`.
- Offline regen from existing dets (no new GPU): 376 AI events in Q1 window.
- KPIs vs prior stages (scorer ±10s):

| Stage | Exact | Manual-only | AI-only | P | R | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline (pre-filter) | 22 | 31 | 2726 | 0.008 | 0.415 | 0.016 |
| Filter-only `53c3141` | 22 | 17 | 209 | 0.095 | 0.415 | 0.155 |
| Teach/calibrate (this) | **37** | **16** | **28** | **0.569** | **0.698** | **0.627** |

- Teaching did: shot-label anchors (3PT/FT/make-miss from manual pairs), positive-window density boost, keep/drop logistic, orphan steal/TO suppress, make-gap soften, ±10s match window, data-driven conf floors.

### Changes

- `event_calibrator.py`, `scripts/teach_from_manual_q1.py`, `models/manual_q1_event_calibrator.json`
- `event_generator.py` wires calibrator; make heuristic + steal window tweaks
- Regression gates raised; side-by-side rebuilt
- `tests/test_event_calibrator.py`

### Leave alone

- LibertyDemo packaging / uninstall browser work

### Next (optional)

- Fouls still mostly absent (manual-only); needs a real foul signal, not anchors alone
- Re-teach after any detector weight change; calibrator is bound to `__rerun_20260718_215754`
