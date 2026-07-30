# Active Task

Updated: 2026-07-29 (learning status nightly report)


Branch: `cursor/full-film-panel-ac1f`


## Meta

| Field | Value |
| --- | --- |
| **id** | full-film-panel |
| **status** | `implemented` |
| **assigned_to** | cursor-agent |


## Objective

Fixed full-film learning evaluation panel with Scott’s hard targets (100% final score, 100% player points, ≥90% event P/R). Hook into teach loop after each successful teach. Nightly daily git save restores + emits `docs/LEARNING_STATUS.md`.


## Checklist

- [x] Recover missing teach/compare sources (`compare_ai_to_hoops_pbp`, `teach_from_*`, `manual_vs_ai_q1_compare`, `boxscore_constraints`)
- [x] `scripts/score_full_film_panel.py` + targets JSON
- [x] Hook `hoops_teach_loop.py` (PANEL log lines; exit 0 on gate fail)
- [x] `docs/FULL_FILM_PANEL.md`
- [x] Lightweight tests
- [x] Run baseline panel (compare-only)
- [x] Restore `daily_git_save.ps1` + installer + `DAILY_GIT_SAVE.md`
- [x] `scripts/generate_learning_status.py` → `docs/LEARNING_STATUS.md`
- [ ] PR merge when Scott asks


## Report

### Proven

- Targets locked: final_score 1.0, player_points 1.0, event P/R ≥ 0.90
- All six panel analysis keys have events in DB (Idaho City full rerun present)
- Nightly learning status report generated; Task Scheduler **Liberty Daily Git Save** Ready @ 11:00 PM
- Teach loop + analysis_launcher + Flask left running during this work

### Inferred

- Opponent half of final_score is not available from current Liberty-oriented AI events → `final_score_status=partial` until opponent scoring is tagged
- HUDL remaining ≈ videos/film_tool total − taught hudl_* keys (not guaranteed 1:1 with reruns)

### Unknown

- Chronological panel trend until ≥2 distinct history snapshots exist


## Ops note

Do not kill Horseshoe `analysis_launcher` or the teach loop. Panel is compare-only. Do not run `daily_git_save.ps1` mid-session if you need to inspect uncommitted work first.
