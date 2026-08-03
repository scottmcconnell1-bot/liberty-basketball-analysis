# Active Task

Updated: 2026-08-01 (ink path hug + no synthetic pass)


Branch: `cursor/full-film-panel-ac1f`


## Meta

| Field | Value |
| --- | --- |
| **id** | playbook-sheet-align |
| **status** | `implemented` |
| **assigned_to** | cursor-agent |


## Objective

Sheet Play All: red travel paths + tokens hug black sheet ink; no invented passes; one beat at a time; white underlay; reset sheet 1.


## Scott recording complaint (2026-08-01 233251)

1. Red SVG travel paths did **not** follow black sheet ink.
2. Players did not follow black sheet lines either.
3. Extra Pass #1→#2 (synthetic) should not be there.


## Fix

### A) Ink tracing (`playbook_sheet_align.py`, cache `v9`)

- Stroke mask minus thick court lines; morphological **skeleton** centerline.
- A* on distance-to-skeleton cost + greedy ink walk + corridor snap candidates.
- Pick candidate with best skeleton ink hit (reject 2-point endpoint-only “perfect ink” on digit blobs).
- Rub 0089→0090 live API: o2 ratio **1.83**, o3 ratio **1.62** (curved); o1 short stay ~straight.

### B) No synthetic passes (`templates/playbook.html`)

- Removed `inferPassReceiver` invent of Pass #1→#2 when digit paths empty.
- Pass beats only from stored movements / explicit pass paths.

### C) Unchanged

- One beat at a time; white underlay court; digit end snap; reset sheet 1.


## Checklist

- [x] Recording frames reviewed earlier (`_review_frames3`); red cut across black ink confirmed
- [x] Synthetic pass removed from served HTML (`Do NOT invent synthetic passes`)
- [x] Flask-only restart (teach loop + analysis_launcher left running); :8080 up
- [x] Live `POST /api/playbook/sheet-paths` returns curved o2/o3 polylines
- [x] `tests/test_playbook_sheet_align.py` 5 passed
- [ ] Scott confirms red hugs black on Play All + no extra pass


## Report

### Proven

- Served playbook HTML: no “Synthetic teaching pass”; has “Do NOT invent synthetic passes”
- Live sheet-paths API (page_0089→0090): o2 n=56 ratio=1.83; o3 n=56 ratio=1.62; o1 ratio=1.00
- Overlay proof `_ink_trace_proof/page_0089_paths.png`: o2 ink_hit≈82%, o3≈64% vs straight ~48%/15%
- Flask pid restarted only; teach `hoops_teach_loop` + `analysis_launcher` still alive
- Sheet1 OCR positions identical to sheet2 → 0 digit travel paths (pass was invented before)

### Inferred

- Sheet1 dashed ink 1→2 is a real drawn pass; removing synthetic means that beat won’t animate until ink-pass detection exists
- End digit on next sheet can differ from arrow tip on current sheet → path may leave tip and finish at OCR end

### Unknown

- Whether Scott wants ink-detected pass animation on sheet1 (dashed arrow) without inventing from jersey geometry
- Screen T-bar vision (still geometric heuristic)


## Ops note

Do not kill `analysis_launcher` / `hoops_teach_loop` when restarting Flask.
