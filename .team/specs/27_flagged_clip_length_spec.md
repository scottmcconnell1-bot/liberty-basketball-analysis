FLAGGED CLIP LENGTH SPEC v1 - run once 2026-11-03: PASS (Cursor coded; 96 tests; 39400 71 frames, 2417100 63, 2753100 16 + double-tag note; 0 other clips changed; gray 31 orange 9; Muse AGREE code) - page: Liberty_Shot_Outputs/review_queue/page_v3/review.html
VETTED by Claude Code, 2026-11-03: plan is Claude Code's prompt restated (Hermes added no arithmetic), so Claude Code adds it here: 39400 clip 977..1047 = 71 frames; 2417100 clip 60420..60482 = 63 frames; 2753100 clip 68820..68835 = 16 frames (7 after the tag <= 14) -> note 'next tag only 0.1 s later - may be the same shot tagged twice'. Clip end comes from the next shot's moment, no new number; flagged shots only; results files only read; no core file, model or banned trial. Coder notes: the 'program's moment' frame label stays at BEFORE (tag frame) for flagged clips; the storage-key change alters review.html for every page, so 'flag off' identity is checked on the jpg files plus the html with only the key line differing.

## Facts

- Spec 26 (PASS, read `.team/specs/26_clip_moment_fix_spec.md`) flags the earlier shot of a pair whose `anchor_frames` are within 23; its clip is `tag_frame - 8 .. tag_frame + 14` (BEFORE=8, AFTER=14 in `.team/shot_detectors/make_review_queue_page.py`). Code: `.team/shot_detectors/clip_moment_fix.py` `resolve_clip_centres`; page builder flag `--clip-moment-fix`.
- Tag frame marks RELEASE (Claude Code verified: shooter releasing/still holding ball at tag frame for 39400 and 2753100). At 25 fps, 14 frames = 0.56 s after release the ball has not reached the rim.
- Three flagged shots:
  - 39400: tag frame 985, next shot 41900 anchor 1048
  - 2417100: tag frame 60428, next 2419200 anchor 60483
  - 2753100: tag frame 68828, next 2753200 anchor 68836 (next tag only 0.1 s later — possibly same shot tagged twice; Scott: question can wait)
- Page bug: `localStorage` key `coach_review_v1` is the same on every page built, so calls from first page carried over to page_v2 (39400 showed "make" from old page).
- Rules: no core file edits; models and `ball_confidence` unchanged; `applied_to_core` false; no banned trials; no tuning after results; Adrian Q4 never used to design; any new number from existing code (name it) or "Scott decides before the run". Make/miss result files never written.

## Plan

1. **Flagged shots only**: clip runs from `tag_frame - BEFORE` to `(next shot's anchor_frame - 1)`, i.e. up to just before the moment that belongs to the next shot. No new number. Unflagged clips unchanged. If that end is at or before `tag_frame + AFTER` (too short, e.g. 2753100: 68835 - 68828 = 7 frames after the tag), keep the clip to that end and the card note adds `"next tag only X.X s later - may be the same shot tagged twice"` (X.X from the two tag times). Show arithmetic for the three shots (clip first/last frame, length).
2. **Page storage key** includes the output folder name (or a build stamp) so each built page keeps its own calls.
3. **Where**: `clip_moment_fix.py` (return a clip end per flagged shot, or a separate small function) and `make_review_queue_page.py`; default behaviour with `--clip-moment-fix` off stays byte-identical in clips.
4. **Tests**: clip end = next anchor - 1; too-short case gets the note; unflagged unchanged; storage key differs between two out dirs.
5. **One run**: rebuild page with the fix to a NEW out dir; pass = only the 3 flagged shots' clips change, their lengths match the arithmetic, gray 31 orange 9.
6. **Roles**: Claude Code vets, Muse checks, Cursor codes (Scott: use Cursor until it runs out).

Every fact from a file you read or the lines above; otherwise "NOT FOUND - Claude Code to check".