# Active Task

Updated: 2026-08-08 (Play All dead — scrub abort + timeline gate)

Branch: `cursor/full-film-panel-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | playbook-play-all-scrub-abort |
| **status** | `implemented` |
| **assigned_to** | cursor-agent |

## Decision (Scott)

1. ▶ Play All / playbar Play must animate tokens again (nothing moves = broken).
2. Prefer Play All works even if playbar timeline still building — never silent no-op.
3. Flask-only restart if templates need it; do not kill teach/analysis.
4. No commit this slice.

## Diagnosis

### Proven

- Continuous-slide slice added `updatePlaybarUI` → programmatic `scrub.value` + `playbarSuppressScrub` cleared on `setTimeout(0)`.
- Chrome/deferred range `input` then called `playbarScrubTo` → `playbarApplyKeyframe` **without** `fromPlay`/`keepPlaying` → cleared `playAllRunning` / bumped `sheetMoveGen` **before first rAF**.
- `playbarPlayThrough` loop: `if (!isPlaybackActive()) break` → zero moves; looked like “Play All doesn’t work at all.”
- Node proof (`SCRUB_RACE_OLD` aborted; `SCRUB_RACE_NEW` stayed active; healthy rAF **144** frames / 2300ms; mid-abort **3** frames).
- Served `http://127.0.0.1:8080/playbook/play/100` already includes `playbarSuppressGen` + `playSheetsDirectly` (Jinja re-reads template; teach PID 36304 untouched).

### Inferred

- Same race after each `playbarCommitIndex` → `updatePlaybarUI` could also kill Play mid-run once a beat started (same deferred `input`).

### Unknown

- Browser MCP could not drive a live click this session; Scott hard-refresh QA still the visual check.

## Shipped this slice

1. **Same-index scrub ignore** while playback active (`playbarScrubTo`).
2. **`playbarApplyKeyframe`** only stops Play on a *different* scrub index (not programmatic re-apply).
3. **Stronger scrub suppress** (`playbarSuppressGen` + double-rAF + timeout).
4. **`playSheetsDirectly` fallback** — sheet→sheet `playActionBeats` if timeline empty / ≤1 kf.
5. **`playAnimation` / playbar ▶** raise flags early; `Promise.race` timeline build (~80ms) then playbar or fallback — never wait forever / no-op.
6. Align completion does **not** `invalidatePlaybarTimeline` while playback active.

## Verify (Scott)

1. Hard refresh playbook **view** (e.g. play 100 / multi-sheet import).
2. ▶ Play All — tokens **slide**; button becomes ⏹ Stop.
3. Console after a beat: `window.__playbookAnimStats.frames` ≫ 1 (often ~100+).
4. Playbar ▶ from mid-timeline also moves; scrub to a *new* beat still pauses/snaps; same-position sync must not stop Play.
5. Teach/analysis still running if they were (only Flask served new HTML).

## Report

### Proven

- Root cause: deferred scrub `input` aborted Play before animation.
- Fix + fallback in `templates/playbook.html`; proof script results above; template live on :8080.

### Inferred

- Coaches can Play immediately while timeline/ink build continues in background.

### Unknown

- Feel of fallback vs playbar path on densest imports after hard refresh.
