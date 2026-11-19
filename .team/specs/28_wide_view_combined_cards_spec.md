WIDE VIEW + COMBINED CARDS SPEC v1 - run once 2026-11-03: PASS (Cursor coded; 103 tests; off = page_v3 clips; on: gray 30 orange 9, groups 86/96/31 frames, 42 shots; Muse AGREE code) - page: Liberty_Shot_Outputs/review_queue/page_v4/review.html
VETTED by Claude Code, 2026-11-03, with corrections the coder must follow: (1) group clip END = max(anchor_frame over the group) + AFTER, not the last shot's anchor: group 2's first shot 2417100 has anchor 60501 > 2419200's 60483, so the spec's end 60497 would cut off 2417100's own moment. Correct lengths: group 1 977..1062 = 86, group 2 60420..60515 = 96, group 3 68820..68850 = 31. (2) Counts: 41900 is gray today and 2419200 / 2753200 are auto misses, so with the flag on: gray cards 30 (41900 moves into group 1), orange cards 9 (6 unflagged orange + 3 combined), 39 cards, 42 shots on the page; the 'gray 31 / orange 10 / 41 cards' line is wrong. (3) Wide-view size is display only, not a detection number: wide frame scaled to 640 px wide (keeps aspect; read frame size with cv2). Wide frames only for cards on the page (~39 cards), not 158 shots. (4) Roles: Scott already named Cursor. Display-only; results files only read; no core file, model or banned trial.

# Wide View + Combined Cards Spec v1

## Facts (from Specs 26, 27 and code read this session)

- Page builder `.team/shot_detectors/make_review_queue_page.py` (flags `--clip-moment-fix`, `--out-dir`); conflict logic `.team/shot_detectors/clip_moment_fix.py` (`resolve_clip_centres` returns `clip_centres`, `flags`, `extents`; `CONFLICT_FRAMES = 23`).
- Each card today is a rim close-up crop (HALF_W 170, ABOVE 150, BELOW 190 around track hoop, x2 upscale), frames `anchor-8 .. anchor+14` (23 frames).
- Spec 27 run (page_v3) FAILED Scott's purpose: clip 977..1047 (39400) shows no ball near rim 977..1022; from ~1027 a ball comes down and goes through at ~1047 = Dayley's make (41900, anchor 1048). Ending a clip just before the next shot's anchor still shows the next shot in the air.
- Scott's notes on page_v3: 19:26.8 (adrian t=1166800, orange, not flagged): "without seeing players I cannot tell if this is a game shot or not." 45:53.1 (2753100): "Not enough footage to tell".
- Pairs whose anchor_frames are within 23 (all 158 shots, 25 fps):
  1) (39400 tag frame 985, anchor 1045) + (41900 anchor 1048, tag frame 1048)
  2) (2417100 tag frame 60428, anchor 60501) + (2419200 anchor 60483)
  3) (2753100 tag frame 68828, anchor 68836) + (2753200 anchor 68836)
- Tag time for these misses marks the RELEASE (Claude Code verified: shooter releasing/still holding ball at tag frame).
- Video frame size: NOT FOUND - Claude Code to check (read it with cv2 in the code, do not assume).
- Rules: no core file edits; models and `ball_confidence` unchanged; `applied_to_core` false; no banned trials; no tuning after results; Adrian Q4 never used to design; no new number unless from existing code (name it) or "Scott decides before the run". Make/miss result files only read. Pages stay local (minors in film).

---

## A. Wide View (display only — nothing changes any program call)

Every card also shows the **whole camera frame** (downscaled, no crop) for the **same frames** as its close-up, side by side or stacked, in step (one slider/play controls both).

- Downscale factor: NOT FOUND in existing code — **Scott decides before the run** (recommend 0.25x or 0.3x so a 1920x1080 frame fits ~480x270 beside the 680px close-up).
- File-size cost: each card writes `2 × n_frames` JPEGs (close-up + wide). For the three combined groups below: Group 1 (86 frames) = 172 files, Group 2 (78 frames) = 156 files, Group 3 (31 frames) = 62 files. Other cards: 23 frames × 2 = 46 files each. Total extra JPEGs ≈ (158 − 6) × 23 × 2 + 172 + 156 + 62 = **~7,200 additional JPEGs** vs page_v3.

---

## B. Combined Cards (replaces Spec 27's clip end for flagged pairs)

When shots `i` and `i+1` are flagged by `resolve_clip_centres` (chain: if `i+1` is also flagged with `i+2`, all join one card), the page shows **ONE card for the group**.

- **Clip** = `(first shot's tag_frame - BEFORE) .. (last shot's anchor_frame + AFTER)` — uses only existing `BEFORE=8`, `AFTER=14` from `make_review_queue_page.py`.
- The card lists **one row per shot** (clock, Make / Miss buttons) plus a **group button "Same shot, tagged twice"** (meaning: count only the last shot of the group).
- **Export** gives each shot its own row (`coach_call` = make / miss / duplicate).
- **Summary table** counts each shot once; a duplicate counts as nothing.
- Card colour: **orange**.

### Arithmetic for the three groups (all 25 fps)

| Group | Shots | First tag_frame | Last anchor_frame | Clip start (first tag - 8) | Clip end (last anchor + 14) | Frames |
|-------|-------|-----------------|-------------------|----------------------------|------------------------------|--------|
| 1 | 39400 + 41900 | 985 | 1048 | 977 | 1062 | **86** |
| 2 | 2417100 + 2419200 | 60428 | 60483 | 60420 | 60497 | **78** |
| 3 | 2753100 + 2753200 | 68828 | 68836 | 68820 | 68850 | **31** |

Gray/orange counting rule per shot unchanged otherwise.

---

## C. Where (new code — pure functions, testable without video)

### In `clip_moment_fix.py`

```python
def group_flagged_chains(
    shots: List[Dict[str, Any]],          # one film, sorted by t
    conflict_frames: int = CONFLICT_FRAMES,
) -> List[List[Dict[str, Any]]]:
    """
    Returns list of groups; each group is a list of consecutive shots where
    each adjacent pair has |anchor_i - anchor_{i+1}| <= conflict_frames.
    A shot not in any conflict is a group of length 1.
    """
    ...
```

### In `make_review_queue_page.py`

- New flag `--wide-combined` (default off; off = page_v3 behaviour unchanged except nothing).
- When on:
  - Call `group_flagged_chains` per film after `resolve_clip_centres`.
  - For each group: compute clip start/end as above, extract frames once, write both close-up and wide-view JPEGs.
  - Build one card per group with per-shot rows + "Same shot, tagged twice" button.
  - Export JSON includes `coach_call` per shot; summary counts duplicates as zero.

---

## D. Tests (pytest, pure, no video)

1. `group_flagged_chains`: pair → 1 group of 2; chain of 3 → 1 group of 3; no flag → each shot its own group.
2. Clip extent of a group: start = first.tag_frame - 8, end = last.anchor_frame + 14.
3. Export rows: each shot in group gets a row; duplicate row has `coach_call = "duplicate"`.
4. Summary counting: duplicate adds 0 to makes/misses; last shot of group counts normally.

---

## E. One Run to a NEW Out Dir

Pass criteria:
- **3 combined cards** with the exact arithmetic lengths above (86, 78, 31 frames).
- All other cards keep their close-up frames **identical to page_v3** and **gain a wide view** (same frame indices, downscaled whole frame).
- Counts: **gray 31**; **orange cards = 10** (7 unflagged review + 3 combined groups). Total cards shown = **41**. Total shots = **158** (unchanged).

---

## F. Roles

- **Claude Code** vets (diff, tests, run output).
- **Muse** checks (AGREE/DISAGREE on VETTED/PASS).
- **Cursor** codes.
- **Scott** names coder, approves merge.

---

Every fact from a file read this session or the lines above; otherwise "NOT FOUND - Claude Code to check".