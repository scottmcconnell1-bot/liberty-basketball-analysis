# Net check (Task 1 step 3)

Read-only measurement of orange pixels in the net ROI for a few frames after the ball reaches the rim. Uses the same 140 tagged build-set shots, hoop boxes, and peak frames as `measure_net_moved.py` / `build_review_page.py` (via `net_moved_build_results.json`). Does not edit or call into any detector; summary thresholds are reporting-only.

```bash
# Windows (checker / Claude Code with venv)
.venv\Scripts\python.exe .team/shot_detectors/pixel_miss/net_check.py --out C:\Users\scott\Documents\Liberty_Shot_Outputs\net_check

# WSL sandbox
python3 .team/shot_detectors/pixel_miss/net_check.py --out .team/shot_outputs_test/net_check
```

# Ball in net (Task 1 step 4)

Read-only measurement: run the existing `models/ball_detector.pt` on frames after the rim (`peak+1`..`peak+6`) and ask whether a ball centre lands in the net ROI. Two columns, no upscaling — **A** = 640×640 native window on the net box (not production scale); **B** = full frame at `imgsz=640` (production scale). Same 140 build-set shots / hoop / peak frames as `net_check.py`. Confidence read-only from `film_analysis.db` (never lowered). Nothing applied to any detector.

```bash
# Windows (checker / Claude Code with venv)
.venv\Scripts\python.exe .team/shot_detectors/pixel_miss/ball_in_net.py --out C:\Users\scott\Documents\Liberty_Shot_Outputs\ball_in_net

# WSL sandbox
python3 .team/shot_detectors/pixel_miss/ball_in_net.py --out .team/shot_outputs_test/ball_in_net
```
