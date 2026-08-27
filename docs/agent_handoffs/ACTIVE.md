# Active Task

Updated: 2026-08-26 (Correct scorebook-only + tip_off)

Branch: `cursor/film-tool-review-layout-ac1f`  
Base: `jason-5-may-updates`

## Meta

| Field | Value |
| --- | --- |
| **id** | adrian-accuracy-quality |
| **status** | `in_progress` |
| **assigned_to** | cursor-agent |
| **scope** | **Adrian JrHigh only** until Scott says accurate |

## Why

Correct dialog was keeping sticky `/api/players` tagging names (Daly, unkn…). Opening tip was stored as `jump_ball` so it did not read as tip.

## Done (Proven)

- Opening tip is **`tip_off`** @ ~3.3s (tracker #2); tip-scramble rebounds not promoted
- Correct: scorebook roster only; sticky Daly/unkn tagging list hidden when scorebook loads
- Program summary exposes scorebook `players` for the dropdown
- Re-refine stable (tip_ms stays ~2.9s, not drift to scramble)

## Try

1. Hard-refresh Film Tool → Show ledger plays → first row **tip_off** (not rebound)
2. Correct → scorebook names only (#40 Dayley · Liberty…)
3. Tip type = **tip_off (opening tip)**; jump_ball = mid-game held ball only

## Next

1. Tip winner jersey/team via lookaround
2. Spot-check timing on NFHS film
3. Unresolved OCR jersey links

## Do not

- Unpause teach loop / flip auto-accept
- Quality on other games yet
