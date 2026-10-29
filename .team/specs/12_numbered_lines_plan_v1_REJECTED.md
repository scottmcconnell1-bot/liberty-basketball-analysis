REJECTED by Claude Code, 2026-10-27 (v1; stamp written late at 15:35 because the Vetters first stamp command crashed): (1) misses requirement 12b: squares S1, S2...; an EDITABLE order box per line; the same number = at the same time; per-line type/player menu; "skip". (2) "Drills = master pages 1-206" is wrong: identify drills and scouting plays by the page header text, never a page range. (3) wrong PDF: C:\Users\scott\Documents\Basketball\Plays\Fast Scout Plays 2021-2022.pdf is a 1-page cover; the 380-page master is C:\Users\scott\Documents\liberty-basketball-analysis\dist\docs\imports\Fast Scout Plays 2021-2022.pdf. (4) the ball-handler ring is around ANY player digit, not only player 1. (5) a file:// page cannot Save: put the entry page in the program and Save through the existing PUT /api/playbook/choreography/<id>. (6) scoring must map each of the 14 hand-made plays to its PDF pages via play_steps.source_image (DB read-only, mode=ro). (7) data/playbook/choreography/*.json are tracked in git: test on copies outside the repo, never the live files.

# Number-the-lines Play Entry Tool — Plan

**Branch:** `team/playbook`
**Date:** 2026-10-27
**Author:** Architect (Hermes)
**Stages:** 1 (extractor fixes + numbered images + scoring) → 2 (order-entry page)

---

## Goal

Build a "number the lines" play-entry tool per Scott's requirement (item 12):
- Fix the extractor problems listed in item 12
- Show each sheet with lines numbered; Scott types order like `"1, 2+3, 4"` (+ = at same time) and can override type (`"4 screen"`) or player (`"2 is player 5"`)
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
| **Ball-handler ring counted as a line** | `_extract_ink` line 633: `L < 130 and closed loop` filters some but not all | Tighten: detect small closed circles near digit 1 (ball-handler); `radius < 15pt` → discard as mark, not path |
| **Bezier curves sampled, not chords** | `_poly_from_drawing` lines 437-455: samples at t=0.25,0.5,0.75,1.0 | Keep sampling but increase resolution (t steps = 10); also expose raw bezier control points for later curve rendering |
| **Screens with T-foot not separated** | `_has_screen_foot` lines 704-718: dot-product threshold 0.35 | Add perpendicular-foot length check; split stroke at foot junction → two segments: main cut + screen foot (type=screen) |

---

## Stage 1 — Extractor Fixes + Numbered Images + Scoring (no UI)

### Deliverables

1. **Fixed `playbook_vector_extract.py`** with the five fixes above
2. **Numbered-line PNG generator** → outputs to `/mnt/c/Users/scott/Documents/Liberty_Play_Catalog/numbered/<play_id>/page_XXX_numbered.png`
   - Each play stroke drawn with its sequence number (1, 2, 3…) at mid-point
   - Court outline, digits, and player rings shown for reference
   - Color: passes=blue, cuts=green, dribbles=orange, screens=red
3. **Scoring script** `scripts/score_numbered_lines.py`
   - Input: auto-built choreography JSON (from fixed extractor) + 14 hand-made JSON files
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

REM 2. Generate numbered images for master PDF pages 1-4 (demo) + all play pages
C:\Users\scott\Documents\liberty-basketball-analysis\.venv\Scripts\python.exe -m scripts.generate_numbered_lines ^
    --pdf "C:\Users\scott\Documents\Basketball\Plays\Fast Scout Plays 2021-2022.pdf" ^
    --out "C:\Users\scott\Documents\Liberty_Play_Catalog\numbered" ^
    --pages 1-380

REM 3. Score against 14 hand-made plays
C:\Users\scott\Documents\liberty-basketball-analysis\.venv\Scripts\python.exe scripts/score_numbered_lines.py ^
    --auto-dir "C:\Users\scott\Documents\Liberty_Play_Catalog\numbered" ^
    --hand-dir "C:\Users\scott\Documents\liberty-playbook\data\playbook\choreography" ^
    --tolerance 15 ^
    --out "C:\Users\scott\Documents\Liberty_Play_Catalog\scoring_report.md"
```

### How Scott Checks by Eye (Stage 1)

1. Open `C:\Users\scott\Documents\Liberty_Play_Catalog\numbered\<play_id>\page_XXX_numbered.png`
2. Verify:
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

## Stage 2 — Order-Entry Page (standalone local page)

### Deliverables

1. **Single HTML file** `tools/numbered_lines_entry.html` (opens in browser, no server)
   - Loads numbered PNGs from local `file://` paths
   - Left pane: image with numbered lines (click to highlight)
   - Right pane: text box for order entry
     - Format: `"1, 2+3, 4"` (comma = sequence; + = simultaneous)
     - Override tokens: `"4 screen"`, `"2 is player 5"`, `"3 pass"`
     - Parse → structured order list
   - **Save** button → writes choreography JSON to `data/playbook/choreography/<play_id>.json` (exact format per 101.json)
   - **Preview** button → renders animation in-page using existing Play All logic (import `static/js/player-viewer.js` functions)
2. **Parser module** `tools/numbered_lines_parser.py` (shared by HTML via Pyodide or called from CLI)
   - `parse_order(text: str, line_count: int) → list[dict]` returns `[{seq, line_nums[], type_override?, player_override?}]`
   - `build_choreography(parsed_order, extractor_output) → dict` emits exact JSON shape

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
REM Open the entry page (no server needed)
start "" "file:///C:/Users/scott/Documents/liberty-playbook/tools/numbered_lines_entry.html"

REM Or serve locally if Pyodide needed
C:\Users\scott\Documents\liberty-basketball-analysis\.venv\Scripts\python.exe -m http.server 8765 --directory "C:\Users\scott\Documents\liberty-playbook\tools"
REM then open http://localhost:8765/numbered_lines_entry.html
```

### How Scott Checks by Eye (Stage 2)

1. Open page → select a play from dropdown (lists all numbered folders)
2. Verify image shows correct line numbers matching the PNG
3. Type order: `"1, 2+3, 4 screen"` → press **Preview**
4. Watch animation: player 1 moves on line 1; players 2&3 move together on lines 2&3; line 4 is a screen (perpendicular foot)
5. Press **Save** → confirm `data/playbook/choreography/<play_id>.json` written
6. Hard refresh main program `/playbook` → open same play → banner says "saved choreography" → ▶ Play All matches entry

---

## Files per Stage

### Stage 1
- `playbook_vector_extract.py` (modified — five fixes)
- `scripts/generate_numbered_lines.py` (new)
- `scripts/score_numbered_lines.py` (new)
- Output: `C:\Users\scott\Documents\Liberty_Play_Catalog\numbered\` (PNGs, not in repo)
- Output: `C:\Users\scott\Documents\Liberty_Play_Catalog\scoring_report.md` (not in repo)

### Stage 2
- `tools/numbered_lines_entry.html` (new, standalone)
- `tools/numbered_lines_parser.py` (new)
- Output: `data/playbook/choreography/<play_id>.json` (written only on Save; in repo but gitignored per existing pattern)

---

## Constraints Checklist

- [ ] No schema change (uses existing JSON shape)
- [ ] Live DB read-only (no writes to DB)
- [ ] Outputs outside public repo except code (numbered PNGs, scoring report to Liberty_Play_Catalog)
- [ ] Drills excluded (skip master PDF pages 1-206 per item 10)
- [ ] Scouting plays excluded (skip "RimRock", "Victory" etc. per item 10)
- [ ] N fixed before scoring: **N = 15 SVG court units**
- [ ] 14 hand-made plays are the answer key (files listed above)

---

## Acceptance Criteria

**Stage 1 PASS** when:
- All 5 extractor fixes verified by eye on demo pages 1-4
- Numbered PNGs generated for all non-drill, non-scouting play pages
- Scoring report shows ≥ 80% lines matched, ≥ 85% type correct on ≥ 10 of 14 plays

**Stage 2 PASS** when:
- Scott can open page, type order, preview animation, press Save
- Saved JSON loads in main program `/playbook` and Play All matches
- No server required (file:// works)