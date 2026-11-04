BIGGER WIDE VIEW SPEC v1 - run once 2026-11-03: PASS (Cursor coded; 103 tests; close-ups identical to page_v4; wide 1920x1080; gray 30 orange 9, 42 shots; 296 MB) - page: Liberty_Shot_Outputs/review_queue/page_v5/review.html
VETTED by Claude Code, 2026-11-03: display only, one file, no call or detection number changes. Correction: 2083 is ALL files; about half are wide jpgs, so the disk estimate is ~half of the spec's (order of a few hundred MB, fine on local disk). Page stays local (minors).

## Facts (from Spec 28 and code read this session)

- Page builder `.team/shot_detectors/make_review_queue_page.py` (flag `--wide-combined`); Spec 28 run produced `page_v4` at `Liberty_Shot_Outputs/review_queue/page_v4/review.html` with gray 30, orange 9, groups 86/96/31 frames, 42 shots.
- Wide frames today: written at 640 px wide (display only, downscaled from source), shown beside the close-up in a card of min width 340 px (CSS `.wrap grid minmax(340px,1fr)`).
- Source video is 1920x1080 (Claude Code verified: wide jpgs downscaled from it; size NOT FOUND as a constant in code — read with cv2).
- Page_v4 has 2083 files (Claude Code counted).

---

## Plan (display only, changes no call, no new detection number)

### 1. Wide frames written at full source width (no downscale)
- Write each wide-view JPEG at 1920x1080 (source resolution).
- Disk cost estimate: ~2083 wide JPEGs × ~150 KB (typical 1920x1080 JPEG) ≈ **312 MB additional** vs page_v4's current wide frames.

### 2. Layout: wide view FULL card width ABOVE the close-up
- Each card becomes one column (grid min width = 100% or the wide image's display width, whichever is wider; state it as `minmax(100%, 1fr)` effectively one card per row on wide screens).
- Wide view on top, close-up below, same slider/play controls both (unchanged from Spec 28).
- Clicking the wide view opens it full-screen (same frame, same controls; Esc or click outside closes). No new frame extraction.

### 3. Where: `make_review_queue_page.py` only, under `--wide-combined`
- Spec 28 behaviour otherwise unchanged.
- Close-up frames remain **byte-identical** to page_v4.
- No changes to `clip_moment_fix.py`, detection, or any core file.

### 4. Tests
- No pure helper added; the check is the **one run** (step 5).

### 5. One run to a NEW out dir
Pass criteria:
- Close-up JPEGs **identical to page_v4** (byte-for-byte).
- Wide JPEGs are **source size (1920x1080)**.
- Same cards and counts as page_v4: **gray 30, orange 9, 42 shots**.
- Page JS passes `node --check`.

### 6. Roles
- **Claude Code** vets (diff, tests, run output).
- **Muse** checks (AGREE/DISAGREE on VETTED/PASS).
- **Cursor** codes.