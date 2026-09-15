# Active Task

Updated: 2026-09-14 (Jason optimize: precision ON + auto-accept 0.85)

Branch: `cursor/film-tool-review-layout-ac1f`  
Related: PR #147 ideas applied locally (precision + auto-accept)

## Dual-machine roles (locked)

| | **Home** | **School / remoted Cursor** |
| --- | --- | --- |
| Data | Source of truth | Funnel only — never overwrite home DB |
| Code | git push/pull | Same |

Funnel: https://liberty-coach.tail368a37.ts.net

## Just enabled (Scott asked to optimize)

| Setting | Value | Effect |
| --- | --- | --- |
| `ai.event_generator_mode` | **precision** | Quieter event list on **next** rebuild/reanalyze |
| `ai.auto_accept_event_confidence` | **0.85** | Auto-keep pending AI events ≥ 85% confidence |
| Ball detector / `ball_confidence` | **unchanged** | Still gated |

**Restart Flask** so `event_generator.py` code loads. Existing Adrian ledger is **not** rewritten until you rebuild events / reanalyze.

## Product focus

Adrian JrHigh accuracy still the review target; precision mode helps future runs.

## Do not

- Change production `ball_detector.pt` / `ball_confidence` without Scott
- Expect gameplans / practice plans / accurate box scores from AI alone yet
