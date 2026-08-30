# Active Task

Updated: 2026-08-29 (black overlay fix + steal vs rebound)

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

Black full-page overlays on Film Tool load (broken HTML + duplicate report drawer). Rebound @ ~11s was steal.

## Done (Proven)

- Fixed `startersDialog` (`</dialog>` not `</div>`); removed duplicate report drawer in film_tool.html
- `ensureFilmToolOverlaysClosed()` on init — closes stuck dialog backdrops
- Fake rebounds before steal dropped; steal labels show stealer + victim

## Try

1. Hard-refresh Film Tool — page should be clickable/typeable immediately (no black flashes)
2. Show ledger → ~13s = steal (not rebound @ ~11s)

## Do not

- Unpause teach loop / flip auto-accept
- Quality on other games yet
