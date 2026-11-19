CLIP SECONDS SPEC v1 - run once 2026-11-03: PASS (Cursor coded; 105 tests; 89-frame clips x36, groups 152/162/97; gray 30 orange 9, 42 shots; 1.0 GB) - page: Liberty_Shot_Outputs/review_queue/page_v6/review.html
VETTED by Claude Code, 2026-11-03: numbers are Scott's (2.0 s / 1.5 s, decided before the run); display only; group arithmetic checked (935..1086=152, 60378..60539=162, 68778..68874=97). Correction: page has 39 cards = 36 normal (30 gray + 6 orange) + 3 combined, so normal frames 36 x 89 = 3204, total 3615 (page_v5 had 1041 per view), ~3.5x -> roughly 1 GB on local disk. Python round(37.5) = 38 (as spec).

SCOTT-DECIDED NUMBERS (before the run):
- CLIP_BEFORE_S = 2.0
- CLIP_AFTER_S = 1.5
- fps = 25
- BEFORE_FRAMES = round(2.0 * 25) = 50
- AFTER_FRAMES = round(1.5 * 25) = round(37.5) = 38

NORMAL CARDS (39 cards: 30 gray + 9 orange):
- frame span: anchor - 50 .. anchor + 38 (inclusive) = 89 frames per card
- total normal frames: 39 * 89 = 3471 frames

COMBINED GROUPS (group_clip_extent with before=50, after=38):
- group 1: tag 985, anchors 1045, 1048 -> first frame 935, last frame 1086, length 152 frames
- group 2: tag 60428, anchors 60501, 60483 -> first frame 60378, last frame 60539, length 162 frames
- group 3: tag 68828, anchors 68836, 68836 -> first frame 68778, last frame 68874, length 97 frames
- total combined frames: 152 + 162 + 97 = 411 frames

DISK COST ESTIMATE vs page_v5 (296 MB):
- page_v5 normal: 42 cards * 23 frames (8+1+14) = 966 frames
- page_v5 combined: 86 + 96 + 31 = 213 frames
- page_v5 total: 1179 frames
- new total frames: 3471 + 411 = 3882 frames
- ratio 3882 / 1179 ≈ 3.3× -> ~976 MB rough estimate

TESTS:
- seconds_to_frames(seconds, fps) helper: round(seconds * fps)
- group_clip_extent with before=50, after=38

ROLES:
- Architect: this spec
- Coder: implements in make_review_queue_page.py (and passes before/after to group_clip_extent; no change to its maths)
- Vetter: verifies frame counts match arithmetic above; page JS node --check
- Muse: checks vetter

PLAN (display only, changes no call):
1. Add constants CLIP_BEFORE_S / CLIP_AFTER_S with comment "Scott 2026-11-03" in make_review_queue_page.py.
2. Under --wide-combined, before/after in frames = round(CLIP_BEFORE_S * fps), round(CLIP_AFTER_S * fps) per film fps (25 -> 50 and 38). Applies to every card (close-up and wide) and to group_clip_extent's before/after. The "program's moment" frame label stays at index = before frames. Flag off: unchanged.
3. One run to a NEW out dir: pass = same cards and counts (gray 30, orange 9, 42 shots); every clip length matches the arithmetic above.
4. Roles: Coder implements, Vetter verifies, Muse checks.