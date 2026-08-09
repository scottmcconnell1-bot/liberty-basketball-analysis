# Active Task

Updated: 2026-08-08 (hide printed sheet digits)

Branch: `cursor/full-film-panel-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | playbook-hide-sheet-digits |
| **status** | `implemented` |
| **assigned_to** | cursor-agent |

## Decision (Scott)

Triangle looks good except: **large black numbers can go away.** Keep colored tokens + useful sheet ink. Prefer toggle off by default (do not delete OCR detection). No commit this slice.

## What the numbers were (Proven)

Printed OCR player digits **1–5** baked into the play-sheet underlay PNG (same glyphs sheet-align detects). Not the small colored SVG tokens.

## How removed

- New layer `#sheetDigitMaskLayer` between underlay and arrows/tokens.
- `renderSheetDigitMasks()` paints white disks (r=40) at **this sheet’s** OCR centers after underlay draw.
- Default **off** (digits hidden). Reveal: `window.__playbookShowSheetDigits = true` or `body.playbook-show-sheet-digits` (CSS `display:none` on mask layer).
- OCR / sheet-align / Triangle choreography unchanged.

## Verify

- Play 127: 5 masks, 5 offense tokens, Triangle hooks live; ring sample around tokens **darkFrac=0**.
- Play 125 (Rip): same mask behavior.
- Teach **36304** / analysis **32384** untouched; Flask **8760**.

Hard refresh: `http://127.0.0.1:8080/playbook/play/127`

## Note

`templates/playbook.html` was briefly zeroed by an editor EMFILE failure mid-slice; restored by replaying transcript StrReplace patches onto HEAD, then digit-mask applied. Spot-check Play All if anything feels off.

## Report

### Proven

- Served HTML includes `sheetDigitMaskLayer` + `renderSheetDigitMasks`; masks=5 on 127/125.
- Pixel ring around tokens shows no remaining black digit ink.

### Inferred

- r=40 is enough for Liberty sheet stencils; very large circled digits on other books might need a bump.

### Unknown / remaining

- Whether Scott wants a visible UI toggle (vs console/CSS only).
