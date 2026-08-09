# Active Task

Updated: 2026-08-08 (Play All — nothing moves / pathLen 0)

Branch: `cursor/full-film-panel-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | playbook-play-all-nothing-moves |
| **status** | `implemented` |
| **assigned_to** | cursor-agent |

## Decision (Scott)

1. ▶ Play All must visibly slide tokens (nothing moves = broken).
2. Hard-refresh QA on play **125** (Step 1/3 — Page 120) from the new recording.
3. Flask-only restart; do **not** kill teach/analysis.
4. No commit this slice.

## Recording (Proven)

File: `20260808-0632-06.9291524.mp4` (~4.6s, 19 samples @4fps).

- Banner **Ready to play**; Step **1 / 3 — Step 1 (Page 120)** (= play **125**).
- ▶ Play All hovered/clicked; tokens stay put; step never advances.
- Dashed ink arrow visible (sheet underlay); playbar below fold / not obvious in crop.
- Court pixel diffs near zero late in clip (no token travel).

## Root cause (Proven)

Prior scrub-abort fix was **live** but incomplete. Two killers stacked:

1. **Deferred scrub `input` with a stale index** after `updatePlaybarUI` changed `max`/`value` — `sameIndex` guard was not enough; Play could die before / during rAF. Recording often never held ⏹ Stop.
2. **`normalizeAnimPath` preferred `toRaw[pid]` over `path.to`.** On play 125, OCR digit positions are **identical** sheet→sheet (`delta=0` for o1–o5). Forced / ink destinations collapsed to `pathLen: 0` → rAF ran but token did not travel (or only wobble then snap back via `syncPlayerTokens(toRaw)`).

## Shipped this slice

1. **Hard scrub isolation while playing** — ignore all scrub `oninput` unless `playbarUserScrubbing` (pointer on thumb); do **not** write `scrub.value`/`max` during `isPlaybackActive()`.
2. **Play All → `playSheetsDirectly` only** — no playbar timeline race on toolbar ▶.
3. **`forceGuaranteeBeats`** — if no travel paths, still build a cut (movements → residual → ball-handler toward farthest teammate / synthetic nudge).
4. **`normalizeAnimPath`** — keep `path.to` when sheet pose is stationary but path has real travel (≥8px).
5. **Land on `animPath.to`** / sync `live` end poses — do not snap back to stationary `toRaw`.
6. Flask restarted (new listener); teach **36304** untouched.

## Verify (Scott)

1. Hard refresh `http://127.0.0.1:8080/playbook/play/125`.
2. ▶ Play All → button **⏹ Stop**; token **#1 slides** (~2.3s) along a path (not a teleport).
3. Console: `window.__playbookAnimStats.frames` ≫ 50 (live proof saw **~299** / 2300ms, `pathLen≈282`).
4. Teach still running (`python` PID 36304 / teach loop).

## Report

### Proven

- Recording: Ready + Play All + static tokens on play 125 / Page 120.
- OCR sheet deltas all **0**; old normalize collapsed forced path to **pathLen 0**.
- After fix (headless Edge): `normTo` keeps forced destination; o1 `translate` samples move continuously; **maxFrames 299**; markers served; scrub hard-gate proof OK; teach alive.

### Inferred

- Same OCR-stationary pattern on other multi-page imports without `movements_json` — guarantee + normalize fix unblocks them.

### Unknown

- Whether forced “toward farthest teammate” always matches the printed ink arrow; ink-trace still preferred when endpoints move.
