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

1. **Pass vs cut** — tip near another digit → `pass` (Triangle p127: 4 strokes → 4 passes including o5→o1 / o3→o5; Pitt 5 p173: o4↔o5 mutual passes on what look like screen/cut strokes).
2. **Nearest-digit start + max_dist** — Rip p122 drops a stroke whose start is >~60px from any digit.
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

- Raw: 2 play + 1 dribble; interp: dribble o1 (71 pts), cut o2; **1 play stroke unattributed**

### Triangle p127

- Raw: 4 play strokes; interp: paths o1/o5/o3 + passes o1→o2, o5→o1, o1→o3, o3→o5

### Pitt 5 p173

- Digits spread (corners/blocks); interp: passes o4→o5 and o5→o4 (likely cut/screen misclass)
