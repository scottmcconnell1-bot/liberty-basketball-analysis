# Active Task

Updated: 2026-07-19
Branch: `cursor/improve-ai-from-manual-q1-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | improve-ai-from-manual-q1 |
| **status** | `completed` |
| **assigned_to** | cursor-cloud-agent |

## Report

### Proven

- Manual Q1 Wilder ground truth: 53 action tags. Baseline AI (`__rerun_20260718_215754`): exact 22 / manual-only 31 / AI-only 2726 (P≈0.008, R≈0.415, F1≈0.016).
- Mismatch pattern: secondary-pass shot flood → paired false DefRebound/Block; auto-accept left human_verified=1 AI events that `persist_events` did not replace on regenerate.
- Offline reprocess from existing detections (no new GPU): `scripts/regenerate_events.py` → 599 AI events in Q1 window.
- After filters: exact **22** / manual-only **17** / AI-only **209** → P **0.095** / R **0.415** / F1 **0.155** (regression gates pass).
- Side-by-side rebuilt: `tag-exports/manual_vs_ai_q1_side_by_side.md` (~20/33/225 — label mapper differs slightly from scorer).

### Changes

- `event_generator.py`: stricter shot arcs, disable speculative blocks/fouls, temporal NMS + shot rate cap, satellite make/miss/rebound linking, steal/TO rate cap, regenerate clears auto-accepted AI (keeps coach-corrected).
- `tag-exports/score_manual_q1_regression.py` + `tests/test_manual_q1_regression.py`
- Film-tool / compare label mapping: OffRebound + shot_type from details
- Windows-safe ball-interpolation log (`->` not unicode arrow)

### Leave alone

- LibertyDemo packaging / install browser work on other branches

### Next (optional)

- Court-geometry 3PT/FT classification (7 manual 3PT + 2 FT still weak)
- New GPU pass only if detections change; event regen from dets is enough for these filters
