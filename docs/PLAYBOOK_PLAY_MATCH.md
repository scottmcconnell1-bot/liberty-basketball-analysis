# FastDraw play / set matching (MVP)

Updated: 2026-08-09  
Branch: `cursor/fastdraw-play-match-ac1f`

## What it does

For a film game with detections (and preferably possession windows), rank
possession movement against the Liberty playbook vector library:

1. **Library fingerprint** from sticky choreography JSON
   (`data/playbook/choreography/{play_id}.json`) when present; else
   `play_steps` positions / movements.
2. **Film fingerprint** from person detections in each possession window
   (tracker_id tracks when available; nearest-neighbor linking otherwise).
3. **Score** = weighted formation similarity + path-displacement similarity
   + optional action-bag overlap.
4. **Output** = suggested play name with **confidence-as-rank** (1 = best
   among loaded library). Suggestions only — **never auto-accepted**.

## Try

```
/film/<stored_filename>/plays?game_id=<analysis_key>
```

Or open Film Tool and use the **Play / set suggestions** panel → Refresh matches.

APIs:

- `GET /api/film/<game_id>/play-matches` — cached JSON side file
- `GET /api/film/<game_id>/play-matches?refresh=1` — recompute
- `POST /api/film/<game_id>/play-matches/run` — force recompute

Cache: `data/play_matches/{game_id}.json` (no `schema.sql` change).

## Limits (MVP)

- No court homography — film points are normalized to the possession’s own
  player cloud, not absolute half-court SVG coordinates.
- Scores are **ranks within the loaded library**, not calibrated probabilities.
- Sticky choreography is the strong path; missing sticky/steps weakens matches.
- YOLO `tracker_id` is unstable; spatial linking is approximate.
- Does not write play calls to the official ledger; auto-accept stays off.

## Not in this slice

- Highlight reel generation (#6)
- Auto-accept of play suggestions
- Schema changes for a `play_matches` table
