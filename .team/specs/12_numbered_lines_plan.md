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
| **Inbounder outside court box** (player 3 above baseline) | `_extract_digit_positions` line 412: `pad = 8.0` clips digits outside court | Expand search pad for digits; allow baseline/halfcourt margin; associate inbounder by proximity to baseline digits |
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
   - Output: choreography JSON per play → `/mnt/c/Users/scott/Documents/Liberty_Play_Catalog/auto_choreography/<play_id>.json` (exact format per 101.json)
4. **Scoring script** `scripts/score_numbered_lines.py`
   - Input: auto choreography JSON (from builder) + 14 hand-made JSON files
   - Output: per-play report + summary table
   - **N (court units tolerance) fixed in this plan before scoring:** `N = 15` (SVG court units; court is 500×470)

### Scoring Metrics (per play)

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
```

### How Scott Checks by Eye (Stage 1)

1. Open `C:\Users\scott\Documents\Liberty_Play_Catalog\numbered\<play_id>\S1_page_XXX_numbered.png` (and S2, S3...)
2. Verify:
   - Square label S1, S2... visible at top-left
   - Inbounder (player above baseline) has a digit and a line number
   - Arrowheads are **not** separate line numbers
   - Ball-handler ring has **no** line number
   - Curved lines show smooth sampling (not straight chords)
   - Screen T-feet show as separate line numbers with type "screen"
3. Read `scoring_report.md` — confirm each of 14 plays shows:
   - Players placed within 15 units: target ≥ 4/5
   - Lines matched: target ≥ 80%
   - Type correct: target ≥ 85%
   - Sequence correct: target ≥ 80%

---

## Stage 2 — Order-Entry Page (Flask route + template)

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
- Output: `C:\Users\scott\Documents\Liberty_Play_Catalog\numbered\` (PNGs, not in repo)
- Output: `C:\Users\scott\Documents\Liberty_Play_Catalog\auto_choreography\` (JSON, not in repo)
- Output: `C:\Users\scott\Documents\Liberty_Play_Catalog\scoring_report.md` (not in repo)

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

---

## Acceptance Criteria

**Stage 1 PASS** when:
- All 5 extractor fixes verified by eye on demo pages 1-4 (master PDF pages 1-4)
- Numbered PNGs generated for all non-drill, non-scouting play pages (drills/scouting excluded by header text)
- Auto choreography JSON built for all extracted plays
- Scoring report shows ≥ 80% lines matched, ≥ 85% type correct on ≥ 10 of 14 plays

**Stage 2 PASS** when:
- Scott can open page at `http://localhost:5000/playbook/numbered-lines/<play_id>`, select play, switch squares S1/S2...
- Each line shows editable order box, type dropdown, player dropdown
- Same number on two lines → Play shows simultaneous movement
- Skip option works
- Shortcut `S2: 1, 2+3, 4` fills boxes correctly
- Press Save → JSON written to `data/playbook/choreography/<play_id>.json` via `PUT /api/playbook/choreography/<id>`
- Saved JSON loads in main program `/playbook` and Play All matches entry
- Testing uses COPY of DB and data/playbook at `C:\Users\scott\Documents\Liberty_Playbook_TestDB`, never live files