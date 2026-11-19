CLIP MOMENT FIX SPEC v2 - run once 2026-11-03: PASS (Cursor coded; 91 tests pass; flag off = today's clips; flag on flagged exactly 39400, 2417100, 2753100; gray 31, orange 9; Muse AGREE on code) - page for Scott: Liberty_Shot_Outputs/review_queue/page_v2/review.html
VETTED by Claude Code, 2026-11-03: rule matches Scott's 'a moment cannot belong to two shots'; changes clip/colour/note only, results files untouched, never adds a make; N=23 from the page clip 8+14+1 (not a tuned number); no core file, model, or banned trial. Conditions for the coder: (a) drop adjusted_anchors (always equal to anchor_frame - dead output); (b) 2417100 and 2753100 are auto misses today (not on the page), so the expected run is orange 7 -> 9, gray 31 unchanged; the 'gray decreases' line is wrong; (c) 'gap >= 25' pass line reads as '> 23'; (d) move the scratchpad page builder into .team/shot_detectors/make_review_queue_page.py unchanged before adding the flag, so it is under test; (e) what the tag time marks for a miss is NOT FOUND - the run's clips at tag time are shown to Scott, not judged by code.

# Clip Moment Fix Spec v2

## 1. The Rule (Plain Words)

A moment cannot belong to two shots. When two consecutive shots (ordered by tag time) have anchor_frames within N frames of each other — including negative gaps where the later shot's anchor is earlier — the anchor moment is given to the later shot. The earlier shot then uses its own tag frame as the clip centre, its card is coloured orange, and it carries the note: "program's moment belonged to the next shot - clip shown at the tag time".

Exact rule: For each shot i in a film (ordered by tag time t), let `anchor_i` be its anchor_frame and `anchor_{i+1}` be the next shot's anchor_frame. If `|anchor_i - anchor_{i+1}| <= N`, then shot i is flagged `clip_moment_conflict`. Its clip window becomes `tag_frame_i - 8 .. tag_frame_i + 14` (23 frames centred on the tag frame, where `tag_frame_i = round(t_i / 1000 * fps)`). The arc/rule make/miss decision for shot i still uses the original `anchor_i` (so the program's call is unchanged). The card shows the clip at the tag frame, is coloured orange, and gets the note above. Shot i+1 is unaffected — it keeps its `anchor_{i+1}` and its clip.

If the gap is larger than N, both shots keep their anchor frames and clips exactly as today.

Why this choice: It only changes which frames the clip shows and the card colour/note. It never changes the make/miss result file and never adds a make. The earlier shot's anchor moment is genuinely ambiguous when it sits inside the next shot's physical window (the next shot's ball is already in the air before its own anchor — Spec 25 lesson). Giving the moment to the later shot is the plain, general rule "a moment cannot belong to two shots". Using the tag frame for the earlier shot's clip is a safe fallback: the tag time marks the coach's labelled event time (for a miss, the ball hits the rim; for a make, the ball goes in — NOT FOUND - Claude Code to check which is which for miss vs make tag time definitions).

N (frames): taken from existing code. The clip half-widths used in the page builder are 8 before + 14 after = 23 frames total. The arc windows in keep_ball_detections.py are WINDOW_BEFORE_START=-15 .. WINDOW_BEFORE_END=0 and WINDOW_AFTER_START=1 .. WINDOW_AFTER_END=12. The relevant constant for "moment conflict" is the clip window size 23 (8+14+1 for strict inequality). N = 23. If Scott wants a different N, mark "Scott decides before the run".

Arithmetic for the three known pairs (all at 25 fps):

1) 39400 -> 41900: anchor_39400=1045, anchor_41900=1048. Gap = |1045 - 1048| = 3 <= 23. Conflict. Shot 39400 flagged `clip_moment_conflict`, clip moves to tag_frame_39400 ± [8,14], orange card with note. Shot 41900 unchanged. PASS: 39400's clip no longer shows the 41900 moment.

2) 2417100 -> 2419200: anchor_2417100 = X, anchor_2419200 = X-18 (gap -18). |gap| = 18 <= 23. Conflict. Shot 2417100 flagged, clip moves to its tag frame, orange card with note. Shot 2419200 unchanged.

3) 2753100 -> 2753200: anchor_2753100 = Y, anchor_2753200 = Y (gap 0). |gap| = 0 <= 23. Conflict. Shot 2753100 flagged, clip moves to its tag frame, orange card with note. Shot 2753200 unchanged.

No other consecutive pair in the 158 shots has anchor_frames within 23 frames.

## 2. Where It Plugs In

New module: `.team/shot_detectors/clip_moment_fix.py` with function:

```python
def resolve_clip_anchors(
    shots: List[Dict[str, Any]],  # each has film, t, anchor_frame, fps
    *,
    clip_before: int = 8,
    clip_after: int = 14,
    conflict_threshold: int = 23,  # N from §1
) -> Tuple[Dict[int, int], Dict[int, int], Dict[int, str]]:
    """
    Args:
        shots: List of shot dicts for one film, sorted by t, each with 't', 'anchor_frame', 'fps'.
    Returns:
        (adjusted_anchors, clip_centres, flags) where:
          adjusted_anchors: {tag_ms: anchor_frame_to_use_for_arc_rule}  # unchanged from D1
          clip_centres: {tag_ms: frame_to_centre_clip_on}              # anchor_frame or tag_frame
          flags: {tag_ms: "ok" | "clip_moment_conflict"}
    """
```

Page builder (the script that generates `C:/Users/scott/Documents/Liberty_Shot_Outputs/review_queue/page/review.html`) imports this and calls it per film on the 158 shots before building cards. The page builder uses `clip_centres[tag]` for the clip frame range (`clip_centre - 8 .. clip_centre + 14`); the arc/rule results keep the original `anchor_frame` from D1 via `adjusted_anchors[tag]` (so make/miss is unchanged). Default-OFF flag `--clip-moment-fix` on the page builder; when off, today's page exactly.

## 3. Tests

Hand-made unit tests in the new module (run with pytest):

- Pair with shared moment: shot A anchor=100, shot B anchor=110, N=23 → |100-110|=10<=23. A flagged `clip_moment_conflict`, A clip_centre = tag_frame_A, B clip_centre = anchor_B=110, B flag="ok". Pass.
- Pair far apart: A anchor=100, B anchor=150 → |100-150|=50>23. Both clip_centre = anchor, both flags "ok". Pass.
- Last shot: no next shot → clip_centre = anchor, flag "ok". Pass.
- Equal anchor frames: A anchor=100, B anchor=100 → |100-100|=0<=23. A flagged, A clip_centre = tag_frame_A, B clip_centre = 100, B flag "ok". Pass.
- Negative gap (next anchor earlier): A anchor=100, B anchor=80 → |100-80|=20<=23. A flagged, A clip_centre = tag_frame_A, B clip_centre = 80, B flag "ok". Pass.
- Switch off: page builder without flag uses original anchors exactly for both arc and clips. Pass.

## 4. One Run Acceptance

Run the page builder with `--clip-moment-fix` on all 158 shots. Output: list every shot whose `clip_centre != anchor_frame` or flag == `clip_moment_conflict`.

Pass criteria:
- Shot 39400: clip_centre = tag_frame_39400 (not anchor 1045), flag = `clip_moment_conflict`. 39400's clip no longer shows the 41900 moment.
- Shots 2417100 and 2753100: each clip_centre = its tag_frame, flag = `clip_moment_conflict`.
- No shot with original anchor gap >= 25 from neighbours changes (the three known close pairs are exactly the ones above).
- Gray/orange counts change only for the three flagged shots (each moves to orange with the note; gray count decreases by up to 3, orange increases by up to 3).
- All other 155 shots: clip identical to today (clip_centre = anchor_frame, flag = "ok").
- The arc/rule make/miss calls for all 158 shots are identical to today (verified by comparing `adjusted_anchors` to original anchors).

If any other shot moves or any make/miss call changes, the run fails and Scott decides before re-run.

## 5. Roles

- Architect (Hermes): this spec.
- Coder: Scott names the coder.
- Vetter (Claude Code): checks diff, runs tests, verifies the one run output.
- Muse: AGREE/DISAGREE on VETTED.
- Scott: names coder, approves merge.

---

All facts from files read this session or lines above. Otherwise: NOT FOUND - Claude Code to check.