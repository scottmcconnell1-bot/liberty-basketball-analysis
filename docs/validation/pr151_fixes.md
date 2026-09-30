# Fixes stacked on PR #151: validation log (2026-09-30)

Base: `cursor/playbook-jason-clean-slate-ac1f` @ 5b7c2a3 (PR #151). Everything below
ran in Docker.

## Before and after

| Check | PR #151 (5b7c2a3) | With these fixes |
|---|---|---|
| CI lint (`ruff F821,F811,F823,E9`) | 1 error (`ai_bridge.py:302`) | clean |
| Full CV image (`bash scripts/docker_test.sh`) | 3 failed, 1004 passed | **1016 passed**, 38 skipped |
| CI-like (`bash scripts/docker_test.sh --ci`) | 4 failed, 990 passed | **999 passed**, 29 skipped |

## Each fix: before → fix → after

"Before" is the test failure on 5b7c2a3. Every test passes after the fix, and fails
again when that fix alone is reverted.

| # | Problem | Before | Fix | Test |
|---|---|---|---|---|
| 1 | `ai_bridge._find_best_tracker_match` used `det`, which is not defined there. NameError on the second person detection. | NameError / CI lint F821 | pass `frame_number` in | test_pr151_fixes::test_ai_bridge_tracks_more_than_one_person |
| 2 | `from court_memory import hoop_xy` always failed (it is a method), which left `ball_through_rim` and `net_moved_after_shot` as None | both None | import only the module functions | test_ai_bridge_core_make_functions_import |
| 3 | `ai_bridge` crashed on OpenCV 5 (no `HOGDescriptor`) | AttributeError | create the HOG descriptor only when available (features are placeholders) | test_ai_bridge_tracks_more_than_one_person (on OpenCV 5) |
| 4 | The Docker image shipped **OpenCV 5.0** although the repo pins `<5`: `ultralytics` pulls in `opencv-python` unpinned, which shadows `opencv-python-headless` 4.x | `cv2.__version__ == 5.0.0` | pin `opencv-python>=4.8,<5` in `requirements.docker.txt` | image rebuilt: 4.14.0, `HOGDescriptor` present |
| 5 | `/api/analysis/<rerun key>` jumped to a *newer* run, so an older rerun could not be viewed | `(963, 0) == (1616, 7)` | jump to the newest run only when the game key is requested | e2e/test_journey_film::test_rerun_labels_second_run_keeps_primary_and_compare_lists_both (extended with a second rerun) |
| 6 | `canonical_event_key`: a new rerun with only pending drafts replaced the copy where the coach had accepted or corrected events | newest unreviewed rerun chosen | keep the newest reviewed run when the newest run has no coach decisions; otherwise #151's newest-run rule | test_canonical_key_keeps_the_coach_reviewed_run (4 cases; the two "newest wins" cases pass on both versions) |
| 7 | Highlights looked up events under the game's original key, while the review queue (via #6) served another run | `Prepared 0 highlight moment(s)` | `list_highlight_moments` and `_fetch_trusted_moments_by_ids` use `canonical_event_key` | e2e/test_e2e_flow::test_09_review_ledger_highlights_clips_playlists |
| 8 | The AI line score was 0-0 for every game without a scoreboard track (all but Adrian), under a note saying "four equal slices of the video" | quarters `[0,0,0,0]` for 8 points | with no scoreboard track, fall back to the equal video slices; with a track, an unreadable moment is still left out | test_ai_line_score_uses_video_quarters_without_a_scoreboard_track |
| 9 | An unreadable scoreboard digit was dropped, so `10:59` could read as `1:05` and set the quarter | legal clock from a partial read | keep a `?` placeholder, and reject any clock containing one. Partial scores and fouls now read as None, not a wrong number. | test_unreadable_clock_digit_does_not_make_a_legal_clock, test_fully_read_clock_still_works |
| 10 | `withManDefense` lost the `playHasSheets()` guard, so imported FastDraw/PDF plays got auto defenders | test_playbook_html_has_align_ready_banner failed | guard restored | test_playbook_sheet_align::test_playbook_html_has_align_ready_banner |
| 11 | Two new tests need OpenCV, which CI does not install | failed in the CI-like image | `pytest.importorskip("cv2")` | test_net_motion_makes_a_shot_when_the_ball_box_vanishes, test_net_kick_is_a_make_a_pan_is_not |

## Left for the review (not changed here)

These are design questions for the owner, or findings not reproduced:

- **Draw-tool pins are not saved.** Defenders dragged in the Draw tool (`pinnedDefense`)
  are not in `picturePayload`, and `/playbook/save` stores only positions, movements and
  notes, so the pin is lost. Fixing it needs a small change to the save format.
- **The game key now shows the newest run.** Since #151, the primary run itself is no
  longer viewable by the game key. This is intended, but worth confirming.
- **Not reproduced (from the code review):**
  - `net_kicked` may call front-rim misses makes.
  - `applyTokenDrag` computes defender spots from this step's positions only.
  - `ensure_identity_applied` has an OCR-support gap.
  - `scoreboard_at` scans every sample per event, and the box is built twice.
- **Housekeeping:** root-level one-off scripts (`check_*.py`, `compute_score.py`,
  `explore_events.py`), status `.txt` files, and runtime data under `data/`.
