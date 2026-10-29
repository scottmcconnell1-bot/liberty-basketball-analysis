# Notus reader v9 — PARKED 2026-10-27 14:20 until a stronger coder model is back

Plan NEXT_TASK.md v9 (VETTED; Muse agreed all points; Scott decided on the two DISAGREEs).
Step 0 done: box search shifts all REJECTED (approved boxes are correct; .team/specs/09_box_search_REJECTED.png).
Steps 1+ attempted by OpenCode on the Ollama gemma4 fallback — REJECTED, not usable:
- hue range written as 0..255 (OpenCV hue is 0..179): the hue rule was not applied.
- game A v_min = 13 (near black): the "lit pixels = brighter half" rule was not applied.
- fit_notus_segments.py per-game fit raised RuntimeError for A1 (hole detection); no geometry files; T_on/T_off not measured; gate NOT run (correct to stop).
Holdout untouched. Next: rerun steps 1+ with a stronger coder model; the Vetter checks the frozen numbers against the rule before the gate.

## Scott decision, 2026-10-27 ~17:45
Scoreboard reader SHELVED (not deleted). It is not the make/miss detector: it never sees misses, shooter, or location, and only works when the board is on camera. The stronger coder's time goes to the court-line finder and the make/miss detectors. Scott will re-address the scoreboard later, for fouls, timeouts, and possessions. All files and the v9 plan stay as they are.
