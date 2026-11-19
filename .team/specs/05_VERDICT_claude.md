# Claude Code verdict on 05_reliable_detector_architecture.md — 2026-10-26 21:20

**Direction: approved.** Per-frame court geometry from models/court_keypoint_detector.pt, four independent make/miss signals, disagreements flagged and never guessed, Stage 1 measurement first, measured pass gates.

**Stage 1: VETTED to start, with these corrections:**
- (3) Adrian (LIBERTY_A_v_ADRIAN_H) was played at Adrian's gym, whose length is unknown. Remove the Adrian half-court gate [38, 44]; report Adrian's measured half court instead. Only both Notus games (LIBERTY_H) are at Liberty (92 ft, 40.75 ft from the rim center).
- (4) The meaning of the model's 18 keypoints is unknown. Stage 1 must discover it: number every point on the overlays, and report each index's likely court landmark with the frames that show it. Do not assume the list in section 1.2.
- (5) Use ONE origin: the rim center (FT line +13.75, baseline -5.25, lane ±6), as in ai_bridge.py and pick_court_points.py. The +15/-4 values in section 1.2 are backboard-face values and would shift every position by 1.25 ft.

**Stages 2–5: REJECTED until fixed:**
- (1) Banned trial: "interpolate gaps ≤ 15 frames" (section 5, S4 risk) is linear interpolation, closed in OLLAMA.md and ACTIVE.md. Remove it.
- (2) Voting logic: `agree = votes >= 3` with `call = make if votes >= 3 else miss` flags every clear miss (0–1 votes). Agreement must work in both directions. A scoreboard (S1) disagreement with the video signals always flags. S1 counts only when the board is readable.
- (6) "Modify run_saved_v6_rule" is not additive. Use a new wrapper; the gate rejects removed lines in ai_bridge.py. Changing what counts as a make in production (core definition: ball_through_rim or net_moved_after_shot) is a Scott gate.
- Minor: drop the gemini-upload copy (Gemini is retired).
