# Playbook vector audit

Raw FastDraw PDF vectors vs Liberty `extract_page` / sheet-extract for sample sheets spanning 1-Game, Rip, Triangle, Pitt 5.

| File | Path |
| --- | --- |
| HTML (open this) | [`raw_vs_interpreted.html`](raw_vs_interpreted.html) |
| JSON dump | [`raw_vs_interpreted.json`](raw_vs_interpreted.json) |
| Regenerator | `scripts/playbook_vector_audit.py` |

Also mirrored under `data/playbook/vector_audit/`.

## View

Hard-refresh the HTML, or open:

`file:///C:/Users/scott/Documents/liberty-basketball-analysis/docs/playbook_vector_audit/raw_vs_interpreted.html`

## Global transform bug?

**No.**

Evidence:

- Digits: raw PDF text centers → court SVG matches `extract_page` positions with **max dist = 0.000** on all 5 sheets.
- Court crop identical everywhere: `(44.0, 163.42, 569.0, 618.42)` (matches `_DEFAULT_COURT_PDF`).
- `_pdf_to_svg` keeps PDF Y direction (down+); no Y-flip in the vector path.

## Systematic vs per-play

| Layer | Verdict |
| --- | --- |
| Digit positions / court scale | **Systematic OK** — not the misread source |
| Stroke → path/pass attribution | **Per-play** (shared heuristics, different failures) |

Shared heuristics that fail differently per sheet (not a one-line transform fix):

1. **Pass vs cut** — now **dash pattern** (dashed=pass / solid=cut on this PDF). Old tip≠start rule invented Triangle/Pitt “passes”.
2. **Nearest-digit start + max_dist** — dashed passes use start radius **75** (Rip p122 was 66.7 > old 60).
3. **One path per oid** — longer stroke wins; extras discarded.
4. **Pass also keeps a path** — attributed count can exceed raw stroke count (counting artifact, not a transform bug).

OCR contrast was skipped here (`cv2` missing in `.venv`); vector digits are the Stage-1 source of truth on this branch.

## Samples (quick numbers)

### 1-Game p32

- Digits SVG: o1(255,321) o2(405,237) o3(89,234) o4(198,237) o5(298,239)
- Raw strokes: 2 play (w=2.92) — short toward 5; longer from 3 toward elbow
- Interp: pass o1→o5; cut o3

### Rip p120

- Digits: o1(251,322) … o4(355,90) o5(308,221)
- Raw: 1 play stroke → interp pass o1→o3

### Rip p122

- Raw: 2 play + 1 dribble; interp: dribble o1, cut o2, dashed pass path on o4 (start radius 75)

### Triangle p127

- Raw: 4 play strokes (1 dashed + 3 solid); interp after dash fix: pass o1→o2 only; cuts on solid strokes

### Pitt 5 p173

- Digits spread (corners/blocks); interp after dash fix: **no** passes (solids → cuts), not o4↔o5

## Pass vs cut: code rule vs FastDraw style (2026-08-09)

### Encoding verdict — THIS PDF vs Scott’s typical convention

| Source | Pass | Cut | Dribble |
| --- | --- | --- | --- |
| **Scott’s typical FastDraw mental model** | solid | dash / zigzag cut | wavy |
| **This Fast Scout PDF (Proven attrs)** | **dashed** `dashes=[5.25 5.25] 0`, w≈2.92 | **solid** `dashes=[] 0`, w≈2.92 | **filled** path (`type=f`, dashes=None) |

**Verdict:** Scott’s coaching-style convention is **inverted** relative to this FastDraw export. Liberty classifies from **this book’s** Proven stroke attrs (`dashes` / fill), not the typical mnemonic.

Labeled re-check (Rip / Pitt 5 / 1-Game / Triangle):

| Sheet | Stroke | dashes | Correct label |
| --- | --- | --- | --- |
| Rip p120 | o1→o3 | `[5.25 5.25] 0` | pass |
| 1-Game p32 | o1→o5 | `[5.25 5.25] 0` | pass |
| 1-Game p32 | o3 | `[] 0` | cut |
| Rip p122 | o2 | `[] 0` | cut |
| Rip p122 | o1 | fill | dribble |
| Triangle p127 | o1→o2 | `[5.25 5.25] 0` | pass |
| Triangle / Pitt solids tip-near digit | `[] 0` | cut (not pass) |

### Q1 — What does Liberty use now?

File `playbook_vector_extract.py`, `_extract_ink`:

1. **Dribble:** `fill` set, `color is None`, `len(items) >= 20`, `L > 150` → `marks[oid] = "dribble"`.
2. **Play stroke gate:** stroked (`color` set, no fill), `width >= 2.2`, not court geometry, not short closed circle.
3. **Pass vs cut from `dashes`:** `_has_dash_pattern` → pass; solid `[]` → cut. **No tip≠start invents.**
4. **Attribution:** mover/passer = digit nearest **start** endpoint; receiver = digit nearest **end** (or next-page tip). Start radius 60 (cut) / **75** (dashed pass — covers Rip p122 @66.7).
5. **Orient:** keep PDF endpoint order when start snaps; reverse only if start misses and end hits a digit.

### Q2 — Does FastDraw encode pass/cut/dribble in vector style?

Yes — see encoding table above. `lineCap` / `lineJoin` / `width` / `color` do **not** distinguish pass vs cut — only **`dashes`** (plus fill for dribble).

### Q3 — Nearest-digit: raw distance or start vs end aware?

**Before:** Raw Euclidean distance in PDF space from each **polyline endpoint** (after simplify) to digit centers — **not** midpoint. Orientation tried start within 60px; if miss, reversed and retried. Classification then used tip≠start (so a cut tip near another player became a “pass”). Endpoints were not labeled as semantic start/receiver beyond that reverse heuristic.

**After:** Still endpoint Euclidean distance (not midpoint). Passer/mover is always the digit nearest the **oriented start**; receiver (passes only) is nearest the **oriented end**. Orientation uses dash/style + which end snaps, not tip≠start.

### Q4 — Attribute by stroke start-point?

**Before:** Partially — preferred geometric start, but pass/cut ignored dash and used tip proximity.

**After:** Yes — mover/passer = nearest digit to stroke **start**; pass receiver = nearest digit to stroke **end**. Midpoint is never used for attribution.

### Raw attrs on misclassified / dropped strokes (pre-fix)

| Sheet | Stroke | dashes | Old Liberty label | Notes |
| --- | --- | --- | --- | --- |
| Rip p120 | idx47, 2pts, L=121, start→o1@21.7 end→o3@32.1 | `[5.25 5.25] 0` | **pass o1→o3** (correct) | baseline dashed pass |
| Triangle p127 | idx47, L=126, o1→o2 | `[5.25 5.25] 0` | pass o1→o2 | dashed; true pass |
| Triangle p127 | idx49/51/53 | `[] 0` | **wrong passes** | solid → cut after fix |
| Pitt 5 p173 | idx47/51 | `[] 0` | **wrong mutual passes** | solid → cut after fix |
| Rip p122 | idx71, L=131 | `[5.25 5.25] 0` | **dropped** (start o4@66.7 > 60) | attributed with start radius 75 |

### Verdict — dash + start attribution

**Shipped:** dash→pass / solid→cut; start→mover / end→receiver; dashed start radius 75. Triangle/Pitt no longer invent solid “passes”. Rip p122 dashed stroke attributes to o4.

**Proven:** dash strings from `page.get_drawings()` on labeled sheets; tip≠start removed as classifier.  
**Inferred:** FastDraw draws dashed passes passer→receiver in path order on these samples.  
**Unknown:** whether every dashed stroke in the full book is a pass (some tips miss digits even at 75px).
