# Active Task

Updated: 2026-08-04 (sheet ink mid-path scoring + dual-machine protocol)


Branch: `cursor/full-film-panel-ac1f`


## Meta

| Field | Value |
| --- | --- |
| **id** | playbook-sheet-align |
| **status** | `implemented` (awaiting Scott Play All confirm) |
| **assigned_to** | cursor-agent |


## Objective

Sheet Play All: red travel paths + tokens hug black sheet ink; no invented passes; one beat at a time; white underlay; reset sheet 1.


## Scott recording complaint (2026-08-01 233251)

1. Red SVG travel paths did **not** follow black sheet ink.
2. Players did not follow black sheet lines either.
3. Extra Pass #1→#2 (synthetic) should not be there.


## Fix (this slice + prior)

### A) Ink tracing (`playbook_sheet_align.py`, cache `v9`)

- Stroke mask minus thick court lines; morphological **skeleton** centerline.
- A* + greedy ink walk + corridor snap candidates.
- **2026-08-04:** pick by **mid-path** skeleton ink (spatial margin from endpoints so digit blobs cannot fake a stroke). No connecting ink → prefer short chord.
- Prior home Rub 0089→0090: o2 ratio **1.83**, o3 ratio **1.62** (curved).

### B) No synthetic passes (`templates/playbook.html`)

- Removed `inferPassReceiver` (dead helper deleted 2026-08-04).
- Pass beats only from stored movements / explicit pass paths.
- Regression guard in `tests/test_playbook_sheet_align.py`.


## Checklist

- [x] Recording frames reviewed (`_review_frames3`)
- [x] Synthetic pass removed; `inferPassReceiver` gone
- [x] Flask-only restart on **home** only (teach/`analysis_launcher` left running) — prior session
- [x] Cloud: synthetic ink-hug + no-fake-detour + HTML guard tests (4 passed / 4 skipped without Rub uploads)
- [x] Dual-machine sync docs/script on branch (`docs/DUAL_MACHINE.md`, `scripts/sync_liberty_work.ps1`)
- [ ] Scott confirms red hugs black on Play All + no extra pass
- [ ] Scott runs sync on work PC once (`pwsh -File scripts/sync_liberty_work.ps1`)


## Dual-machine (home ↔ work)

- Shared branch: `cursor/full-film-panel-ac1f`
- Arrive: `pwsh -File scripts/sync_liberty_work.ps1` — Leave: push safe code/docs
- Does **not** sync: `.env`, `film_analysis.db`, `uploads/`, teach/panel runtime
- Details: `docs/DUAL_MACHINE.md`


## Report

### Proven

- Playbook HTML: no `inferPassReceiver` / no “Classic wing: o1 → o2”; has “Do NOT invent synthetic passes”
- Cloud tests: curved stroke ratio ≥1.08 + mid ink ≥0.7; two digit blobs alone → near-chord
- Live DB/uploads/teach state are **home-only** (not in Cloud Agent checkout)
- Dual-machine helper + docs committed on this branch
- Nightly `docs/LEARNING_STATUS.md` (2026-08-02): panel gates still FAIL — separate slice

### Inferred

- Sheet1 dashed ink 1→2 is a real drawn pass; no synthetic means that beat won’t animate until ink-pass detection exists
- Mid-path ink scoring should reduce white-chord / blob-wander on real Rub sheets like synthetics

### Unknown

- Whether Scott wants ink-detected pass animation on sheet1 without inventing from jersey geometry
- Whether home Rub 0089→0090 still matches prior ratios after mid-ink change (home re-check; do not restart teach)
- Whether work PC clone already tracks this remote branch


## Ops note

Do not kill `analysis_launcher` / `hoops_teach_loop` when restarting Flask.
Flask-only restarts: **home learning PC only**. This Cloud Agent does not touch home processes.
