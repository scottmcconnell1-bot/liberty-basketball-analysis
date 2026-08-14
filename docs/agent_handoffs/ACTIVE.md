# Active Task

Updated: 2026-08-12 (Adrian-only accuracy — scorebook quality pass)

Branch: `cursor/film-tool-review-layout-ac1f`  
Base: `jason-5-may-updates`

## Meta

| Field | Value |
| --- | --- |
| **id** | adrian-accuracy-quality |
| **status** | `in_progress` (team PTS match; jersey IDs still wrong) |
| **assigned_to** | cursor-agent |
| **scope** | **Adrian JrHigh only** until Scott says accurate |

## Why

Blind program promote left ~13k accepted events / ~5k AI PTS vs scorebook ~77. CV firehose + tracker IDs ≠ jerseys. One coach cannot clear that by hand.

## Done (Proven)

- `adrian_quality.py` — temporal dedupe + scorebook make/FT caps + heuristic REB/AST/… + reject noise on **all** related keys (base + `__rerun_*`)
- `scripts/refine_adrian_events.py` + `POST /api/program/<game_id>/auto-ledger` runs quality for Adrian (not blind promote)
- Film Tool button: **Build / refine Adrian ledger**
- After refine on `film_analysis.db`: **team ledger PTS 77 = scorebook 77**; FGM 28, TPM 6, FTM 15
- Confidence auto-accept still **locked at 0**
- **Clip review loop**: click a play list row → loops ~2.5s before / ~4s after; dock Accept / Correct / Reject / Next / Stop; advances to next after a decision
- Film Tool declutter: **Watch plays** above **Build the team box**, both arrow-collapsed (`details`); Analysis Results panel removed from Film Tool (link to `/analysis/<game_id>` only)
- Clip reject/advance fix: optimistic UI + seek guard + sticky stage `pointer-events` so Reject removes the row and Next clip starts; list clicks work under the sticky film
- Accept/Reject speed: skip full `refresh_game_stats` on single-event review (~60s → ~30ms); UI no longer waits on the save

## Try

1. Videos → Active → **Liberty vs Adrian (JrHigh) - NFHS clean** → **Review**  
   File: `nfhs_gam0a66d85e12.mp4` · GameID: `jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334`  
   Old `LIBERTY_A_v_ADRIAN_H_…` screen-capture is **Archived** (do not use)
2. Hard-refresh — player sizes to the film (no black side bars)
3. Open **Build the team box** only when refining; day-to-day stay in **Watch plays on film**
4. Scorebook: **Liberty 51 – Adrian 26** (confirmed + photo)
5. Click a play row → looping clip dock → Accept/Reject/Correct or Next
6. Exceptions = jersey/ID mismatches (expected until CV links #13/#40/…)
7. Full shot/possession/minutes panels: use **Analysis Results**, not Film Tool

## Next (still Adrian only)

1. Jersey/track ID linking so player lines match scorebook (Mendoza 13, Dayley 26, …)
2. Timestamp truth-check vs film (caps fix counts, not necessarily timing)
3. Only then expand quality path beyond Adrian

## Do not

- Unpause teach loop (`TEACH_LOOP_PAUSED`)
- Flip `auto_accept_event_confidence`
- Run quality/auto-ledger on other games yet
