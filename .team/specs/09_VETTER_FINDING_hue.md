# Vetter finding, 2026-10-27 — Notus reader fix v4, before step 1 (colour measurement)

Evidence (fitting frames only, .team/notus_fit_crops/*_cell_*.png, all >= 60 s from every gate and holdout time):
pixels with V >= 100 inside the score cells, share whose hue is in the plan's fixed red range [0,12] U [165,180]
versus "yellow" hue (13-40):

- Notus A1: red share 0.56-1.00, yellow share up to 0.44 (e.g. 142 s 0.56/0.44, 3133.5 s 0.57/0.43, 1922.1 s 0.65/0.35).
  By eye, many A1 frames show lit segments with yellow/white cores and red edges (camera exposure); a few are deep red (1518 s, 2565 s).
- Notus A: red share 0.98-1.00 in every frame (pink/red digits).

Consequence: step 1 of NEXT_TASK.md keeps the hue range FIXED at [0,12] U [165,180] and only measures S/V percentiles.
On A1 that rule throws away up to ~44% of the lit pixels (the yellow cores), so the mask would still miss segments on A1
however S/V are set. The hue range must be measured by the same fixed rule on fitting frames, not assumed.

Eye-read values for all 20 fitting frames: .team/notus_fit_crops/eye_read_values.json (80 slot entries).
