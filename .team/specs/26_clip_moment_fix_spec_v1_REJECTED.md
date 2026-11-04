REJECTED by Claude Code, 2026-11-03: (1) self-contradiction: by its own rule 39400 (anchor 1045, next 1048: 1048-15=1033 < 1045-8=1037) is flagged and keeps anchor 1045, yet the pass line requires adjusted anchor <= 1033; (2) ending the clip before the next shot's anchor does not keep the next shot out: the next shot's ball is in the air before its anchor (spec 25 lesson), so 1025..1047 still shows Dayley's shot, not Colman's; (3) negative gap (2417100 -> 2419200, next anchor 18 frames EARLIER) not handled; (4) '15 from WINDOW_BEFORE_START' - that constant is -15 and is the arc window, not a clip rule; (5) says the other two pairs are 'already handled' - NOT FOUND; (6) names OpenCode as coder - Scott names the coder.

CLIP MOMENT FIX SPEC v1 - not run

# Clip Moment Fix Spec v1

## 1. The Rule (Plain Words)

A shot's clip window must never include the next shot's anchor_frame. If it would, the earlier shot's anchor_frame is moved backward (or the shot is flagged) so that its clip ends strictly before the next shot's anchor_frame.

Exact rule: For each shot i in a film (ordered by tag time), let `anchor_i` be its anchor_frame and `anchor_{i+1}` be the next shot's anchor_frame. The clip for shot i is `anchor_i - 8 .. anchor_i + 14` (23 frames). If `anchor_i + 14 >= anchor_{i+1}`, then shot i's anchor_frame is set to `anchor_{i+1} - 15` (so the clip ends at `anchor_{i+1} - 1`). This is the maximum backward move that keeps the clip window valid and non-overlapping. If `anchor_{i+1} - 15 < anchor_i - 8` (i.e., the next shot's anchor is less than 23 frames after the original anchor), the clip window would invert — in that case, shot i is flagged `clip_conflict` and keeps its original anchor; the page shows an orange card with note "clip may show the next shot".

Why this choice: It only moves or flags the clip window; it never changes the make/miss call (which uses the original anchor_frame for the arc/rule). It is the smallest change that guarantees "a moment cannot belong to two shots". The backward move uses the constant 15 from `WINDOW_BEFORE_START` (keep_ball_detections.py:38), so the before-window still has 15 frames if possible.

N (frames) = 23 (clip half-width sum: 8 before + 14 after + 1 for strict inequality). Derived from existing constants, not a new number.

## 2. Where It Plugs In

New module: `.team/shot_detectors/clip_moment_fix.py` with function:

```python
def resolve_clip_anchors(
    shots: List[Dict[str, Any]],  # each has film, t, anchor_frame
    *,
    clip_before: int = 8,
    clip_after: int = 14,
) -> Tuple[Dict[int, int], Dict[int, str]]:
    """
    Args:
        shots: List of shot dicts for one film, sorted by t, each with 't' and 'anchor_frame'.
    Returns:
        (adjusted_anchors, flags) where:
          adjusted_anchors: {tag_ms: adjusted_anchor_frame}
          flags: {tag_ms: "ok" | "clip_conflict"}
    """
```

Page builder (scratchpad `make_review_queue_page.py`) imports this and calls it per film on the 158 shots before building cards. The page builder uses `adjusted_anchors[tag]` for the clip frame range; the arc/rule results keep the original `anchor_frame` from D1 (so make/miss is unchanged). Default-OFF flag `--clip-moment-fix` on the page builder; when off, today's page exactly.

## 3. Tests

Hand-made unit tests in the new module (run with pytest):
- Pair with shared moment: shot A anchor=100, shot B anchor=110 → A adjusted to 95 (110-15), clip 87..109, B clip 102..124, no overlap. Pass.
- Pair far apart: A anchor=100, B anchor=150 → A unchanged (114 < 150). Pass.
- Last shot: no next shot → unchanged, flag "ok". Pass.
- Equal tag times (deduped by next_shot_cuts): both get same next anchor; rule applies to each independently. Pass.
- Switch off: page builder without flag uses original anchors exactly. Pass.

## 4. One Run Acceptance

Run the page builder with `--clip-moment-fix` on all 158 shots. Output: list every shot whose adjusted_anchor != original anchor or flag == "clip_conflict".

Pass criteria:
- Shot 39400: adjusted anchor ≤ 1033 (so clip ends ≤ 1047 < 1048 = next anchor 41900). 39400's clip no longer shows 41900 moment.
- No shot with original anchor gap ≥ 25 from neighbors changes (the three known close pairs: 39400→41900 gap 3, 2417100→2419200 gap -18, 2753100→2753200 gap 0; only 39400 is miss/make, the other two are miss/miss and already handled).
- Gray/orange counts change only for flagged shots (39400 moves from orange to whatever its adjusted clip shows; 2417100 and 2753100 may get flagged if gap < 23).
- All other 155 shots: clip identical to today.

If any other shot moves, the run fails and Scott decides before re-run.

## 5. Roles

- Architect (Hermes): this spec.
- Coder (OpenCode): writes `.team/shot_detectors/clip_moment_fix.py`, adds flag to page builder.
- Vetter (Claude Code): checks diff, runs tests, verifies the one run output.
- Muse: AGREE/DISAGREE on VETTED.
- Scott: names coder, approves merge.

---

All facts from files read this session or lines above. Otherwise: NOT FOUND - Claude Code to check.