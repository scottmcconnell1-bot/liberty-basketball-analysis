VETTED by Claude Code, 2026-10-29 (v4 revision 2, two binding notes): the 5 rejection points are fixed - screen is one line with no number on the bar (eye check item 2); hand-file metrics are reference only with no targets (item 3, acceptance); deviations credited to Hermes's review, not Scott; chained lines use PDF points, two passes repeated until nothing changes, and a distance report before the radius is used; full court detected by outline shape 1.9 vs 0.94 with a 2.5 pt outline and a stroke test between 0.9 and 1.8 pt, and the saved full-court field is put to Scott. Checked by reading the revised sections against the measurements of p144, p157, p163 and templates/playbook.html at HEAD.
BINDING NOTE a (Gap 1, "Radius validation"): the radius has no number in the plan. The coder writes the distance report first, picks ONE radius in PDF points from it, states it and the report to Scott, and only then turns chained attachment on. Any dropped stroke beyond the radius stays dropped and is listed.
BINDING NOTE b (Gap 1 step 3 "flag the line as chained", and Gap 2 court_mode): nothing new is written into the choreography JSON until Scott decides on the format question. The "chained" flag lives only in the completeness report. The full-court field waits for Scott's yes.
SCOTT DECISIONS 2026-10-29: (1) chained lines attach only when the stroke start is within 16 PDF points of the same page's kept line end (dribble tips count) - "2. Yes"; the other dropped strokes stay dropped and listed. (2) court_mode field in the choreography JSON: yes ("Doesn't seem to cost anything to add that step and if it helps, do it"). Binding note b is lifted for court_mode only; the "chained" flag still lives only in the completeness report.
CORRECTION by Claude Code, 2026-10-29 (after Muse DISAGREE): Gap 2 said `setCourtMode()` is at "line ~955"; at HEAD it is at line 916 (`isFullCourt` 655, `renderCourt` 803; checked with `git show HEAD:templates/playbook.html | grep -n`). The text in Gap 2 is corrected. Nothing else in the plan changed. Other line citations checked: the "Problems found" table (lines 403/412, 633, 437-455, 704-718 of playbook_vector_extract.py) describes the extractor BEFORE the Stage 1 fixes and matches `git show db0d2d3^:playbook_vector_extract.py`; at HEAD those parts moved (pad 408, ring check 755, _poly_from_drawing 445, _has_screen_foot 836). After a second Muse DISAGREE (pad = 8.0 is at line 403, not 412) the table cell now says line 403 sets pad and line 412 uses it. Test citations (160-165, 196-199) match tests/test_playbook_vector_extract.py at HEAD.

PLAN v4 - Stage 1 built except grading and the two gaps; v4 changes NOT BUILT YET

VETTED by Claude Code, 2026-10-27 15:35 (v3): fixes all seven v1 points, checked by string search and by reading the changed lines: editable per-line order boxes, the same number = at the same time, squares S1..; drills and scouting excluded by page header text, never a page range; the 380-page master PDF in dist\docs\imports; the ball-handler ring around ANY digit; the entry page is a program route that saves through the existing PUT /api/playbook/choreography/<id> (exists in blueprints/playbook.py); scoring maps the 14 hand-made plays to PDF pages via play_steps.source_image with the DB read-only (mode=ro); testing on a COPY of the DB and data/playbook in C:\Users\scott\Documents\Liberty_Playbook_TestDB. N = 15 fixed before scoring. data/playbook/choreography/101.json is a read-only format reference, not a file the coder changes, so it is not in ## Files. Hermes left a scratch file .hermes/cache/scratch/check_strings.py in the worktree; moved out by the Vetter. Wording edit (Scott, 2026-10-27, after Muse DISAGREE on the stamp only): the scheduling note is kept in 12_numbered_lines_build_SCHEDULE.md; the plan itself is unchanged.

# Number-the-lines Play Entry Tool — Plan

**Branch:** `team/playbook`
**Date:** 2026-10-27
**Author:** Architect (Hermes)
**Stages:** 1 (extractor fixes + numbered images + auto choreography + scoring) → 2 (order-entry page)

---

## Goal

Build a "number the lines" play-entry tool per Scott's requirement (items 12, 12b):
- Fix the 5 extractor problems listed in item 12 (Vetter demo)
- Show each **square** (one diagram = one sheet/phase) with visible number S1, S2...; every line in it numbered
- Each line has a small **EDITABLE order box** pre-filled with the computer's guess; Scott changes numbers and presses **Play** to check
- **SAME number on two lines = they move AT THE SAME TIME** (e.g. lines 4 and 2 both "1" = both cut together, then pass "2")
- A line can be set to **"skip"**
- Line type (pass/cut/dribble/screen) and player can be changed from a small menu next to the box
- Shortcut: typing `S2: 1, 2+3, 4` stays available
- Build choreography JSON in **exactly the existing format** (see `data/playbook/choreography/101.json`)
- Save only when Scott presses **Save**
- Score auto-built choreography against Scott's 14 hand-made plays (`data/playbook/choreography/*.json`)
- **No schema change**, live DB read-only, outputs outside public repo except code
- **Drills and scouting plays excluded** (items 9-10)

---

## Extractor Problems to Fix (item 12, Vetter demo)

| Problem | Location in `playbook_vector_extract.py` | Fix |
|---------|------------------------------------------|-----|
| **Inbounder outside court box** (player 3 above baseline) | `_extract_digit_positions` line 403 sets `pad = 8.0`; line 412 uses it to clip digits outside court | Expand search pad for digits; allow baseline/halfcourt margin; associate inbounder by proximity to baseline digits |
| **Arrowheads counted as separate strokes** | `_poly_from_drawing` + `_extract_ink` filter: no arrowhead detection | Detect filled triangles at stroke ends (area < threshold, 3 vertices); merge into parent stroke; do not emit as separate line |
| **Ball-handler ring counted as a line** | `_extract_ink` line 633: `L < 130 and closed loop` filters some but not all | Tighten: detect small closed circles near ANY player digit (not only digit 1); `radius < 15pt` → discard as mark, not path |
| **Bezier curves sampled, not chords** | `_poly_from_drawing` lines 437-455: samples at t=0.25,0.5,0.75,1.0 | Keep sampling but increase resolution (t steps = 10); also expose raw bezier control points for later curve rendering |
| **Screens with T-foot not separated** | `_has_screen_foot` lines 704-718: dot-product threshold 0.35 | Add perpendicular-foot length check; split stroke at foot junction → two segments: main cut + screen foot (type=screen) |

---

## Stage 1 — Extractor Fixes + Numbered Images + Auto Choreography + Scoring (no UI)

### Deliverables

1. **Fixed `playbook_vector_extract.py`** with the five fixes above
2. **Numbered-line PNG generator** `scripts/generate_numbered_lines.py` → outputs to `/mnt/c/Users/scott/Documents/Liberty_Play_Catalog/numbered/<play_id>/S<square>_page_XXX_numbered.png`
   - Each square (phase) gets visible label S1, S2... at top-left
   - Each play stroke drawn with its line number (1, 2, 3…) at mid-point
   - Court outline, digits, and player rings shown for reference
   - Color: passes=blue, cuts=green, dribbles=orange, screens=red
3. **Auto choreography builder** `scripts/build_choreography_from_extractor.py` (new)
   - Input: fixed extractor output for a play (all squares)
   - Computer guesses order per square: sequential 1..N per square
   - Output: choreography JSON per play → `/mnt/c/Users/scott\Documents\Liberty_Play_Catalog\auto_choreography\<play_id>.json` (exact format per 101.json)
4. **Scoring script** `scripts/score_numbered_lines.py`
   - Input: auto choreography JSON (from builder) + 14 hand-made JSON files
   - Output: per-play report + summary table
   - **N (court units tolerance) fixed in this plan before scoring:** `N = 15` (SVG court units; court is 500×470)

### Grading — Completeness Against the PDF Itself (Scott: "Yes" to grading against the PDF)

**Measured:** scoring against the 14 hand files gave 0/62 lines matched, because the hand files put players at textbook spots, not where the PDF draws them; 5 of 14 are copies of others, 4 have no lines, only 101 (41) and 103 (Crush) are user_save.

**New Stage 1 grade = completeness against the PDF itself:**

FastDraw ends every play stroke with a small filled polygon — an arrowhead (~91 pt around) or a thin screen bar (~64 pt, 29×3 pt), found by `_end_marks()` in `playbook_vector_extract.py`.

**Grade = end marks that end on a KEPT line / all end marks, per page, over all play pages** (drills and scouting excluded).

Current measured value on the 161 play squares: **451 end marks**.

**Pass bar:** ≥ 90% of end marks attach to a kept line (i.e., the stroke that owns the mark is classified and emitted as a line). Report per-page and total.

**Player attribution check:** the line's start digit. A kept line must have a start point that snaps to a digit (o1..o5) within the existing START_DIST thresholds. If a kept line lacks a start digit, it is not counted as a successful attachment.

**Hand files:** kept as a reference report only (the old scoring script runs and its output is included for comparison). Scott still checks the numbered pictures by eye.

### Scoring Metrics (per play) — Reference Report Only

| Metric | Definition |
|--------|------------|
| **Players placed within N** | Count of o1..o5 where `distance(auto_pos, hand_pos) ≤ N` |
| **Lines matched** | Auto stroke ↔ hand stroke: same player, same type, path Hausdorff distance ≤ N |
| **Type correct** | Of matched lines, fraction where `kind` matches (pass/cut/dribble/screen) |
| **Sequence correct** | Of matched lines, fraction where `seq` matches hand order |

### Run Commands (Stage 1)

```cmd
REM 1. Apply extractor fixes (edit playbook_vector_extract.py per plan above)
REM    — manual edit, no command

REM 2. Generate numbered images for play pages only (drills/scouting excluded by header text, not page range)
C:\Users\scott\Documents\liberty-basketball-analysis\.venv\Scripts\python.exe -m scripts.generate_numbered_lines ^
    --pdf "C:\Users\scott\Documents\liberty-basketball-analysis\dist\docs\imports\Fast Scout Plays 2021-2022.pdf" ^
    --out "C:\Users\scott\Documents\Liberty_Play_Catalog\numbered" ^
    --exclude-drills --exclude-scouting "RimRock,Victory"

REM 3. Build auto choreography JSON for all extracted plays
C:\Users\scott\Documents\liberty-basketball-analysis\.venv\Scripts\python.exe -m scripts.build_choreography_from_extractor ^
    --numbered-dir "C:\Users\scott\Documents\Liberty_Play_Catalog\numbered" ^
    --out "C:\Users\scott\Documents\Liberty_Play_Catalog\auto_choreography"

REM 4. Score against 14 hand-made plays (map via play_steps.source_image, DB read-only mode=ro)
C:\Users\scott\Documents\liberty-basketball-analysis\.venv\Scripts\python.exe scripts/score_numbered_lines.py ^
    --auto-dir "C:\Users\scott\Documents\Liberty_Play_Catalog\auto_choreography" ^
    --hand-dir "C:\Users\scott\Documents\liberty-playbook\data\playbook\choreography" ^
    --tolerance 15 ^
    --out "C:\Users\scott\Documents\Liberty_Play_Catalog\scoring_report.md"

REM 5. NEW — Completeness grade (end marks on kept lines)
C:\Users\scott\Documents\liberty-basketball-analysis\.venv\Scripts\python.exe -m scripts.grade_completeness ^
    --pdf "C:\Users\scott\Documents\liberty-basketball-analysis\dist\docs\imports\Fast Scout Plays 2021-2022.pdf" ^
    --numbered-dir "C:\Users\scott\Documents\Liberty_Play_Catalog\numbered" ^
    --out "C:\Users\scott\Documents\Liberty_Play_Catalog\completeness_report.md"
```

### How Scott Checks by Eye (Stage 1)

1. Open `C:\Users\scott\Documents\Liberty_Play_Catalog\numbered\<play_id>\S1_page_XXX_numbered.png` (and S2, S3...)
2. Verify:
   - Square label S1, S2... visible at top-left
   - Inbounder (player above baseline) has a digit and a line number
   - Arrowheads are **not** separate line numbers
   - Ball-handler ring has **no** line number
   - Curved lines show smooth sampling (not straight chords)
   - A screen is **one line**, type "screen", ending at the bar; the bar has **no number**
3. Read `scoring_report.md` — confirm each of 14 plays shows reference metrics only (no targets; hand files are reference only)
4. Read `completeness_report.md` — confirm:
   - Total end marks found (expected ~451)
   - End marks on kept lines / total ≥ 90%
   - Per-page breakdown

---

## Gaps to Plan in Stage 1 (Not Yet Built)

### Gap 1 — Chained Lines (Double p64, Pitt 5 p173, ~73 lines in book)

A player's later line starts where that player's previous line ended (dribble then pass, screen then roll), not at the digit, so it is dropped.

**Examples:**
- Double p64: player 1's cut after the pass
- Pitt 5 p173: player 4's roll after the screen

**Plan for attribution:**
1. After a line is KEPT and its END mark is attached, record the player's end position (the arrowhead tip or screen bar center) in a per-page `player_end_pos[oid]` map.
2. When a new stroke is being attributed, check BOTH:
   - Start near a digit (existing logic, `START_DIST_CUT/PASS`)
   - Start near `player_end_pos[oid]` for the same player on the same page (radius in **PDF points**; every other distance in the extractor uses PDF points)
3. If both match, prefer the digit (earlier beat). If only the end-position matches, attribute to that player and flag the line as "chained".
4. If two different players' end positions are within the radius of the same stroke start, pick the closer one; if tie, pick the player whose previous line was earlier in draw order.
5. Chained lines get their own line number and order box; they are not merged into the previous line.

**Processing order (two passes, not draw order):**
- Draw order is not guaranteed to be time order, so a single pass updating `player_end_pos` after each kept line can miss a chain whose parent is drawn later.
- **Pass 1:** Keep only lines whose start snaps to a digit (existing logic). Record their end positions in `player_end_pos`.
- **Pass 2:** For remaining marked strokes, if the stroke start is within the PDF-points radius of any `player_end_pos[oid]`, attribute to that player, flag as "chained", and update `player_end_pos[oid]` to this stroke's end.
- **Repeat pass 2** until no new strokes are attached in a full sweep.

**Radius validation:** Before the radius is used, the coder reports the start-to-nearest-kept-end distance for every dropped marked stroke on the play pages, so Scott can see the radius is not hiding wrong attachments.

### Gap 2 — Full-Court Pages (p157 Finish the Cycle, transition pages)

Transition pages draw the whole court smaller, with play strokes thinner than 2.2 pt, so no lines are read.

**Measured on p144, p157, p163:**
- Detected court rect (white panel) = 324 × 562 pt (the real outline is 2.7 pt wide; `_detect_court_rect` requires `width >= 3.0`)
- Real court outline = 270 × 508 pt
- Play strokes (cuts, dashed passes) = 1.8 pt
- Court lines = 0.9 pt
- "Court height > 700 pt" never happens

**Detection (shape-based, not height threshold):**
- A page is full-court when the **outline's shape ratio** (height / width) ≈ 1.9 (half-court ratio ≈ 0.94).
- Accept a **2.5 pt outline** (real outline is 2.7 pt; current code requires ≥ 3.0).
- The stroke test must sit between **0.9 pt (court lines) and 1.8 pt (play strokes)**.

**Scaling:**
- When a page is detected as full-court by shape ratio, set `STROKE_WIDTH_THRESHOLD` between 0.9 and 1.8 (e.g., 1.1) and `COURT_H = 940` for SVG mapping.
- The `_pdf_to_svg` function already uses piecewise mapping via landmarks; for full court, add the full-court baseline/halfcourt landmarks (the same three bands, doubled).
- The end-mark detection (`_MARK_MAX_PERIM = 130`) and attachment distances (`_HEAD_ATTACH_DIST = 30`, `_BAR_ATTACH_DIST = 12`) stay in PDF points — no change needed.
- The court outline drawing in `generate_numbered_lines.py` should clip to the detected rect (already does).

**Saving full-court state for Play All:**
- Today `isFullCourt` is only a page toggle in `templates/playbook.html` (the `courtModeSelect` dropdown and the `setCourtMode()` function; at HEAD `isFullCourt` is declared at line 655 and `setCourtMode()` is at line 916). It is **not saved** in the choreography JSON.
- To make Play All use the 500×940 court for a saved full-court play, the choreography JSON needs a field (e.g., `"court_mode": "full"` or `"court_frac": {...}` with full-court coordinates).
- **The plan currently says the format must match 101.json exactly. Adding a field needs to be stated so Scott can decide.** If a field is added, document it here and in the Constraints Checklist.

**Pages affected:** p157 (Finish the Cycle), and any other transition/full-court pages identified by the shape-ratio heuristic.

---

## Accepted Deviations (HERMES: AGREE, 2026-10-29; Muse check pending)

1. **Fix 5 (screen bar):** one screen line ending at the bar (not two segments). The screen foot is not emitted as a separate line; the bar is merged as the stroke's end mark and the whole stroke gets `kind="screen"`. This matches the test `test_screen_bar_marks_a_screen_not_an_arrow` (line 160-165 in test file).

2. **Fix 4 (bezier sampling):** samples 10 points per curve but does **not** add control points to the JSON. The test `test_bezier_sampled_ten_steps` (line 196-199) verifies 11 points (start + 10 samples). The choreography JSON keeps only the sampled polyline; raw control points are not stored.

---

## Stage 2 — Order-Entry Page (Flask route + template) — UNCHANGED

### Deliverables

1. **Flask route** in `blueprints/playbook.py`: `@bp.route('/playbook/numbered-lines/<int:play_id>')`
   - Renders template `templates/playbook/numbered_lines_entry.html`
   - Loads numbered PNGs via static file serving
   - **Left pane:** dropdown to select play; shows squares S1, S2... as tabs; each square shows its numbered PNG
   - **Right pane:** for the selected square, a vertical list of lines — each line row has:
     - **Editable order box** (pre-filled with computer's guess: 1, 2, 3... per square)
     - **Type dropdown** (pass/cut/dribble/screen/skip) — pre-filled from PDF classification
     - **Player dropdown** (o1..o5) — pre-filled from nearest-player attachment
     - **Play button** → renders animation in-page for that square using existing Play All logic (import `static/js/player-viewer.js` functions)
   - **Shortcut text box** at top: accepts `S2: 1, 2+3, 4` format (parses → fills boxes)
   - **Save button** → calls existing `PUT /api/playbook/choreography/<id>` (exact format per 101.json)
2. **Parser module** `tools/numbered_lines_parser.py` (shared by template via Flask render or CLI)
   - `parse_order(text: str, line_count: int) → list[dict]` returns `[{seq, line_nums[], type_override?, player_override?}]` — handles both shortcut format and per-box values
   - `build_choreography(parsed_orders_per_square, extractor_output) → dict` emits exact JSON shape

### Choreography JSON Format (must match 101.json exactly)

```json
{
  "version": 1,
  "play_id": <int>,
  "updated_at": "ISO8601",
  "source": "numbered_lines_entry",
  "sticky": true,
  "steps": [
    {
      "step_index": 0,
      "source_image": "<path>",
      "court_frac": {...},
      "positions": { "o1": {"x":0,"y":0}, ... },
      "coachOrder": true,
      "movements": [
        { "type": "cut|pass|dribble|screen", "timing": "sync", "from": "oN", "to": "oM", "points": [...], "anchors": [...], "shape": "straight|curve|flex", "bend?" }
      ],
      "ink": { "paths": {}, "marks": {}, "passes": [], "actions": [ { "kind": "...", "points": [...], "fromPid": "oN", "toPid": "oM", "seq": N } ] }
    }
  ]
}
```

### Run Commands (Stage 2)

```cmd
REM Stage 2 runs inside the Flask program
REM 1. Route added in blueprints/playbook.py: @bp.route('/playbook/numbered-lines/<int:play_id>')
REM 2. Template: templates/playbook/numbered_lines_entry.html
REM 3. Open at http://localhost:5000/playbook/numbered-lines/<play_id>
REM 4. Save button calls existing PUT /api/playbook/choreography/<id>
REM 5. Test DB copy at C:\Users\scott\Documents\Liberty_Playbook_TestDB (never live files)
```

### How Scott Checks by Eye (Stage 2)

1. Open page → select a play from dropdown (lists all numbered folders)
2. Click square tabs S1, S2... → verify image shows correct line numbers matching the PNG
3. For a square: verify each line's order box pre-filled 1..N; type dropdown shows PDF classification; player dropdown shows nearest player
4. Change order boxes: set lines 2 and 4 both to "1" → press **Play** → watch animation: players on lines 2 & 4 move together
5. Change a line's type to "screen" → press **Play** → verify perpendicular foot renders
6. Set a line to "skip" → press **Play** → verify it doesn't animate
7. Use shortcut box: type `S2: 1, 2+3, 4` → boxes update → press **Play**
8. Press **Save** → confirm `data/playbook/choreography/<play_id>.json` written
9. Hard refresh main program `/playbook` → open same play → banner says "saved choreography" → ▶ Play All matches entry

---

## Files

### Stage 1
- `playbook_vector_extract.py` (modified — five fixes)
- `scripts/generate_numbered_lines.py` (new)
- `scripts/build_choreography_from_extractor.py` (new)
- `scripts/score_numbered_lines.py` (new)
- `scripts/grade_completeness.py` (new — completeness grading against PDF end marks)
- Output: `C:\Users\scott\Documents\Liberty_Play_Catalog\numbered\` (PNGs, not in repo)
- Output: `C:\Users\scott\Documents\Liberty_Play_Catalog\auto_choreography\` (JSON, not in repo)
- Output: `C:\Users\scott\Documents\Liberty_Play_Catalog\scoring_report.md` (not in repo)
- Output: `C:\Users\scott\Documents\Liberty_Play_Catalog\completeness_report.md` (not in repo)

### Stage 2
- `blueprints/playbook.py` (modified — add route `/playbook/numbered-lines/<int:play_id>`)
- `templates/playbook/numbered_lines_entry.html` (new — entry page template)
- `tools/numbered_lines_parser.py` (new — shared parser module)
- Output: `data/playbook/choreography/<play_id>.json` (tracked in git; testing uses COPY at `C:\Users\scott\Documents\Liberty_Playbook_TestDB`, never live files)

---

## Constraints Checklist

- [ ] No schema change (uses existing JSON shape)
- [ ] Live DB read-only (no writes to DB); scoring opens DB via sqlite URI `mode=ro`
- [ ] Outputs outside public repo except code (numbered PNGs, auto choreography, scoring report to Liberty_Play_Catalog)
- [ ] Drills excluded (identified by page header text line 1 containing "Drills", not by page range)
- [ ] Scouting plays excluded (identified by page header text line 1 with team names "RimRock", "Victory", etc.)
- [ ] N fixed before scoring: **N = 15 SVG court units**
- [ ] 14 hand-made plays are the answer key (files listed above)
- [ ] Scoring maps each play_id to PDF pages via `play_steps.source_image` and compares step by step
- [ ] `data/playbook/choreography/*.json` tracked in git; testing runs on COPY of DB and COPY of data/playbook at `C:\Users\scott\Documents\Liberty_Playbook_TestDB`, never live files
- [ ] Square numbering S1, S2... visible on images and in UI
- [ ] Editable order boxes per line (not single text box)
- [ ] Same number = simultaneous (not + notation)
- [ ] Skip option per line
- [ ] Type/player menus per line
- [ ] Shortcut format `S2: 1, 2+3, 4` supported
- [ ] Play button per square for instant preview
- [ ] Entry page served via Flask route in `blueprints/playbook.py` + template; Save uses `PUT /api/playbook/choreography/<id>`
- [ ] **If full-court field is added to choreography JSON for Gap 2, note it here and get Scott's decision**

---

## Acceptance Criteria

**Stage 1 PASS** when:
- All 5 extractor fixes verified by eye on demo pages 1-4 (master PDF pages 1-4)
- Numbered PNGs generated for all non-drill, non-scouting play pages (drills/scouting excluded by header text)
- Auto choreography JSON built for all extracted plays
- **Completeness grade ≥ 90%** (end marks on kept lines / total end marks ≥ 0.90 over all 161 play squares)
- Scoring report shows reference metrics on ≥ 10 of 14 plays (no targets; hand files are reference only)

**Stage 2 PASS** when:
- Scott can open page at `http://localhost:5000/playbook/numbered-lines/<play_id>`, select play, switch squares S1/S2...
- Each line shows editable order box, type dropdown, player dropdown
- Same number on two lines → Play shows simultaneous movement
- Skip option works
- Shortcut `S2: 1, 2+3, 4` fills boxes correctly
- Press Save → JSON written to `data/playbook/choreography/<play_id>.json` via `PUT /api/playbook/choreography/<id>`
- Saved JSON loads in main program `/playbook` and Play All matches entry
- Testing uses COPY of DB and data/playbook at `C:\Users\scott\Documents\Liberty_Playbook_TestDB`, never live files