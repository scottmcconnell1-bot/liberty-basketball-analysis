RIM-FIRST SHOT FINDER SPEC v1 - not run

1. ARCHITECT OPINION ON CLAUDE CODE'S PROPOSAL

AGREE with the core concept: v6 on the hoop crop is proven reliable for make/miss (coach page 41/42 shots correct, 0 differ from tags; collect_q4_bodd.py v6_ball). Using "ball comes DOWN INTO the rim area from above" as the shot trigger leverages this proven reliability and avoids BODD full-frame false positives (spare balls, referee, lights, crowd) that caused spec 33's low SHOT/AIRBALL rates (Adrian 33/109, Notus 5/31).

CHANGE required: The proposal says "run the v6 hoop-crop detector over the whole game." This would require moving the crop to follow the hoop as the camera pans — what the user calls "hoop recenter." The banned list in OLLAMA.md / DETECTOR_PROPOSAL_REJECTION.md / AGENT_OPERATIONAL_PROTOCOL.md explicitly names: linear interpolation, ByteTrack, DeepSORT, early windows, wider column. "Hoop recenter" is not in those files, but the user's prompt adds it to the banned list. In collect_flight_tracks.py (spec 33, VETTED), the v6 crop uses BODD-detected hoop position per frame with fallback to `last_hoop` (lines 367–382) — this IS moving the crop with the pan. If that is the banned "hoop recenter," it was already VETTED in spec 33 and the ban would be new. If "hoop recenter" means post-hoc adjustment during a single shot's flight, my plan avoids it.

MY PLAN: Run BODD full-frame (conf 0.12, imgsz 960) over the whole game to detect the hoop in every frame AND find candidate "ball coming down into the rim zone" moments. At each candidate moment, run v6 crop (conf 0.28, imgsz 640, hx±260, hy-200..hy+240) in a short window (±500 ms) to confirm rim crossing and get precise crossing frame. Then trace backward from that moment using BODD full-frame (not v6) to the shooter's hands → shooter box + floor spot. This uses v6 ONLY where proven (at the rim), avoids continuous v6 and hoop recenter, and drops airballs/hard shots to orange coach cards (Scott's standing rule).

BETTER IDEA: The proposal's "trace backward along the ball that left the rim area" is correct — spare balls/referee/logos never come down into the rim, arcs leaving the top of frame still come back near the rim, short gaps matter less. My plan makes this concrete with existing numbers and a clear BODD→v6 handoff.

2. EXACT DETECTION

2.1 Models, crops, confidence, imgsz (from existing code)

| Component | Model | Crop | Conf | Imgsz | Source |
|-----------|-------|------|------|-------|--------|
| BODD full-frame (scan) | `BODD_yolov8n_0001.pt` | Full frame (1920×1080 Adrian, 1280×720 Notus) | 0.12 | 960 | collect_flight_tracks.py:311–312, 340–342 |
| BODD classes kept | basketball, hoop, player | — | — | — | collect_flight_tracks.py:348–350 |
| v6 ball (confirm at rim) | `ball_net_runs/v6/weights/best.pt` | Hoop crop: hx±260, hy-200..hy+240 | 0.28 | 640 | collect_q4_bodd.py:121–125, v6_ball() |
| v6 crop center | Hoop position at candidate frame (from BODD hoop detection that frame) | — | — | — | collect_flight_tracks.py:367–369, 379–380 |

2.2 "Comes down into the rim area" — precise decision (all numbers from existing code)

A candidate shot moment is a frame `f` where ALL hold:

1. **Hoop detected this frame**: BODD hoop box exists at frame `f` (collect_flight_tracks.py:367–369). Let `(hx, hy, hw, hh)` = that hoop box. `hoop_w = hw`.
2. **Ball detected this frame**: BODD basketball box exists at frame `f` (collect_flight_tracks.py:371–374). Let `(bx, by)` = ball center.
3. **In rim zone**: `dist((bx,by), (hx,hy)) <= rim_contact_dist * hoop_w` where `rim_contact_dist = 0.735 hoop widths` (spec 33, Scott approved; from `court_memory.py:165` `rim_r=72` / Adrian median `hoop_w=98` = 0.735). In px: `dist <= 0.735 * hoop_w`.
4. **At or above rim**: `by <= hy + 40` (from `court_memory.py:190` `y <= hoop_y + 40`). In hoop widths: `(hy - by) / hoop_w >= -40/hoop_w` (ball not far below rim).
5. **Coming DOWN (falling)**: Ball y-coordinate increased from previous frame with ball detection: `by > prev_by` (where `prev_by` is ball y at previous frame where BODD detected a ball). This uses BODD full-frame sequence — no tracker, no gap filling.
6. **Rise before fall (arc gate)**: There exists a prior frame `f_rise < f` (within 3000 ms / 75 frames at 25 fps) where ball was detected AND `by_rise < hy - rim_r` (ball above rim height; `rim_r=72` px from `court_memory.py:165`). Rise in px: `hy - rim_r - by_rise >= 170` px (from `event_generator.py:1071` `rim_arc_shots` `min_rise=170.0`). This mirrors the proven rim arc pattern.
7. **Peak near hoop**: At the highest point (min `by`) between `f_rise` and `f`, distance to hoop <= 280 px (from `event_generator.py:1071` `rim_arc_shots` `max_dist=280.0` AND `court_memory.py:150` `close_to_rim` `max_dist=280.0`). In hoop widths: `peak_dist / hoop_w <= 280 / hoop_w` (≈ 2.86 on Adrian, ≈ 4.34 on Notus).

If all 7 hold → candidate shot moment at frame `f`. Run v6 crop in window `[f - 500 ms, f + 500 ms]` (12 frames each side at 25 fps) to confirm rim crossing and get precise crossing frame.

**New number (Scott decides before run)**: `v6_confirm_window_ms = 500` (proposed). Reason: short window around candidate; v6 only needs to see the rim crossing. If different, Scott overrides.

2.3 Hoop position over the whole game (camera pans) — no banned hoop recenter

BODD full-frame detects the hoop in every frame (collect_flight_tracks.py:340–369). The hoop box `(hx, hy, hw, hh)` is available per frame. For candidate moments, we use the hoop detected **in that same frame** (line 379: `if hoop_box is not None: hx_hy = (hoop_box["x"], hoop_box["y"])`). If BODD misses the hoop in a frame, we do NOT fall back to `last_hoop` for candidate detection — we simply have no candidate that frame. This avoids "hoop recenter" (moving the crop based on stale hoop position). The v6 confirm window uses the hoop position at the candidate frame only (short ±500 ms window, camera pan negligible).

This is NOT the same as collect_flight_tracks.py's `last_hoop` fallback (lines 381–382), which was VETTED for spec 33. My plan: no fallback for candidate detection; v6 confirm uses single-frame hoop position.

3. COST ESTIMATE

| Film | Duration (Q1–Q3) | Frames (25 fps) | BODD full-frame passes | v6 confirm windows (est. candidates) |
|------|------------------|-----------------|------------------------|--------------------------------------|
| Adrian | ~32 min (1920 s) | ~48,000 | 1 | ~150 candidates × 25 frames = 3,750 |
| Notus Q1 | ~8 min (480 s) | ~12,000 | 1 | ~40 candidates × 25 frames = 1,000 |
| **Total** | **~40 min** | **~60,000** | **2** | **~4,750 v6 frames** |

BODD full-frame: ~60,000 frames × 2 films. v6 confirm: ~4,750 frames (only at candidates). **Estimated GPU time: ~8–12 minutes total** (BODD ~30 ms/frame, v6 ~20 ms/frame on GPU). Marked ESTIMATE — real time recorded in run log.

4. MEASURE

Run on Adrian Q1–Q3 (109 tags) + Notus Q1 (31 tags) + fake shots from spec 32 (Adrian Q1–Q3: 106 extra, Notus Q1: 31 extra). Total moments = 140 tagged + 137 fake = 277.

Output dir: `Liberty_Shot_Outputs/rim_first/` (script refuses if exists).

Per moment, using `find_shots_measure.match_shots` (8000 ms window, spec 33):

| Metric | How measured |
|--------|--------------|
| Found / extra per kind | Match finder moments to tags (8000 ms). Report: true positives (matched tagged), false positives (finder only), false negatives (tagged only), per kind (2PT/3PT/FT). |
| Timing error | For matched: `|finder_t_ms - tag_t_ms|` median / max per kind. |
| Release trace + shooter box rate | For each true positive (Rule 2 SHOT): trace backward from v6 confirm crossing frame along BODD full-frame ball track to first frame where ball center inside a player box (distance < max(w,h) × `release_trace_factor` = 0.6, spec 33). Report: success %, median frames back, shooter box (frame, x,y,w,h). No tracker_id. |
| Rim crossing precision | For true positives: v6 crossing frame vs tag frame offset (ms). |
| Orange cards | Moments where candidate detection fired but v6 confirm failed OR trace failed OR ambiguous (gap > 3 frames during trace). Reason recorded. |

**Q4 blind run ONLY after Scott sees Q1–Q3 numbers.** No Q4 data read, detected, or reported in this spec (C5 / VETTED).

5. MAKE/MISS SAFETY

Files and outputs the make/miss path uses (this spec touches NONE):

- `.team/shot_detectors/make_review_queue_page.py` — builds coach review page
- `scripts/build_review_page.py` — alternate review page
- `collect_q4_bodd.py` — collects Q4 v6 tracks (v6_ball function)
- `C:/Users/scott/AppData/Local/Temp/v6_tracks.json` — Adrian Q1–Q3 v6 tracks (111 entries)
- `C:/Users/scott/AppData/Local/Temp/v6_tracks_notus_q1.json` — Notus Q1 v6 tracks (31 entries)
- `Liberty_Shot_Outputs/q4_guard/v6_tracks_q4.json` — Adrian Q4 v6 tracks
- `Liberty_Shot_Outputs/ball_arc/d1_results.json` — D1 results for Adrian Q1–Q3
- `Liberty_Shot_Outputs/d2_train/test2/d2_results.json` — d2v1 results for Adrian Q1–Q3
- `Liberty_Shot_Outputs/review_queue/q4/v6/results.json` — v6 Q4 results
- `Liberty_Shot_Outputs/review_queue/q4/d2v1/results.json` — d2v1 Q4 results
- V6 weights: `C:/Users/scott/AppData/Local/Temp/ball_net_runs/v6/weights/best.pt`
- BODD weights: `C:/Users/scott/AppData/Local/Temp/BODD_yolov8n_0001.pt` (used only for hoop samples in collect_q4_bodd.py)

**Check before and after this spec's run:**

```
.venv python .team/shot_detectors/make_review_queue_page.py --wide-combined --out-dir <NEW_DIR>
```

Verify output:
- `gray=30 orange=9` for Adrian + Notus (42 shots shown on page)
- `v6 mapping check 1.0000` printed (all 42 shots have a hoop entry from v6 tracks)
- Combined groups match page_v6 (printed "combined groups (film, times, first, last, length)")

If any check differs → STOP, Scott decides.

6. CODE

New scripts under `.team/shot_detectors/` (pure functions + tests):

- `rim_first_scan.py` — BODD full-frame scan over whole game, emits candidate moments JSON. No v6.
- `rim_first_confirm.py` — For each candidate, run v6 crop ±500 ms, confirm rim crossing, emit confirmed shots JSON.
- `rim_first_trace.py` — Trace backward from confirmed crossing along BODD track to shooter box, emit final shots JSON.
- `rim_first_measure.py` — Load final shots + tags + fakes, run matching (8000 ms), compute measure tables.

**Rules:**
- No core edits (event_generator.py, ai_bridge.py, court_memory.py, net_detector.py untouched)
- No training (uses existing v6 and BODD weights)
- No banned trials: linear interpolation, ByteTrack, DeepSORT, early windows, wider column, hoop recenter (as defined in section 2.3)
- No tuning after results — all numbers fixed before run (section 2 table + `v6_confirm_window_ms`)
- DB read-only (mode=ro for fake shots)
- Images local only (minor debug crops to `Liberty_Shot_Outputs/rim_first/debug/`)
- Output dir `Liberty_Shot_Outputs/rim_first/` — script refuses if exists

7. ROLES & GATES

- Cursor codes the four scripts + tests (pure functions, hand-made tracks).
- Claude Code vets: no core edits, matching logic correct (8000 ms window, `find_shots_measure.match_shots`), window fixed before run, output dir refusal, no gap filling, "Scott decides" numbers recorded, hoop-relative units used, no tracker_id, teammate part excluded, make/miss safety check before/after.
- Muse checks the Vetter: AGREE or DISAGREE with each VETTED/PASS. A DISAGREE stops the loop for Scott.
- **Stop for Scott with the table** of "Scott decides" numbers (section 2.2 item 7: `v6_confirm_window_ms` proposed 500 ms, plus the seven numbers from spec 33 section 2 table: `rim_contact_dist`, `near_hoop_dist`, `gap_threshold_frames`, `catch_distance_factor`, `release_trace_factor`, `detection_window_before_ms`, `detection_window_after_ms` — all fixed before run).

8. FACT SOURCES

Every fact above comes from a file read this session or the prompt. Otherwise: "NOT FOUND - Claude Code to check".

Key lines read this session:
- `collect_q4_bodd.py:110–146` (v6_ball crop, conf 0.28, imgsz 640, is_make logic)
- `collect_flight_tracks.py:311–314, 340–382, 389–413` (BODD full-frame, v6 crop, last_hoop fallback)
- `event_generator.py:1071–1122` (rim_arc_shots: max_dist=280, min_rise=170, not called in pipeline)
- `court_memory.py:165` (rim_r=72.0), `:190` (dist <= rim_r and y <= hoop_y + 40), `:150` (close_to_rim max_dist=280), `:119–123` (near_basket)
- `ai_bridge.py:1033` (0.55*hoop_w crossing), `:1082` (0.6*hoop_w column), `:1237` (0.85*hoop_w drift veto)
- `manual_tag_teach.py:18` (MATCH_TOLERANCE_MS=8000)
- `.team/specs/33_shot_flight_rules_measure_spec.md` (spec 33 full, Scott-approved numbers, results)
- `.team/specs/34_ball_track_check_spec.md` (spec 34 full, VETTED D1–D6, hand check 20 frames)
- `OLLAMA.md` (banned: linear interpolation, ByteTrack, DeepSORT, early windows)
- `DETECTOR_PROPOSAL_REJECTION.md` (banned: linear interpolation, wider column)
- `AGENT_OPERATIONAL_PROTOCOL.md` (Golden Rules: no loosening, no banned trials, no theater)
- `.team/shot_detectors/make_review_queue_page.py` (coach page, gray/orange logic, wide-combined output)
- ffprobe: Adrian 1920×1080@25fps, Notus 1280×720@25fps
- Tag counts: Adrian 127 total (Q1:44, Q2:25, Q3:40, Q4:18), Notus 31 total (Q1:31)
- Spec 32 fake counts: Adrian Q1–Q3 106 extra, Notus Q1 31 extra
- Spec 33 results: SHOT/AIRBALL only Adrian 33/109, Notus 5/31; fakes removed well; release trace-back 36/38
- Spec 34 results: BODD full-frame vs v6 crop analysis, 20 hand-labelled frames (7 wrong object, 5 ball leaves top, 4 gap, 1 PASS overlap, 3 later moment)