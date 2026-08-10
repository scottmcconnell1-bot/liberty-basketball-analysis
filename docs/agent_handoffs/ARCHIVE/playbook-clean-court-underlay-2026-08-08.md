# Active Task

Updated: 2026-08-08 (clean court: no underlay ink / digit masks)

Branch: `cursor/full-film-panel-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | playbook-clean-court-underlay |
| **status** | `implemented` |
| **assigned_to** | cursor-agent |

## Decision (Scott)

Playbook UI feedback:

1. White `#sheetDigitMaskLayer` disks (r≈40) were blotting court/path ink while hiding OCR digits.
2. Black sheet movement ink (arrows, cuts, T-bars) should not appear on the animated court — tokens + ball are enough.

Prefer clean look: no white circles, no black 1–5 glyphs, no movement ink underlay. Keep OCR/aligner/path detection. Preserve Triangle 127 + Rip 125. No commit.

## Approach

Hide sheet underlay compositing in default animation view (SVG court only). Digit masks cleared / no longer painted. Opt-in slideshow (`__playbookSheetSlideshow`) still shows the raw sheet. Detection APIs unchanged.

## Files

- `templates/playbook.html` — `showSheetUnderlay` skips PNG in animation mode; `renderSheetDigitMasks` clears only
- `static/css/playbook.css` — comment update for retired masks

## Verify

Hard refresh:

- `http://127.0.0.1:8080/playbook/play/125`
- `http://127.0.0.1:8080/playbook/play/127`

Expect: SVG court, colored tokens animate, no white disks, no black sheet ink on court.

Flask restarted on :8080. Teach ports left alone.

## Report

### Proven

- Animation path no longer appends underlay `<image>` or white digit disks.
- Layer `sheetDigitMaskLayer` retained for DOM/test compatibility.
- Live hard-refresh check (Playwright): 125 + 127 → `sheetCourtMode=false`, `underlayHasImage=false`, `maskCircleCount=0`, SVG court paths present, 5 offense tokens idle and during Play All.
- Flask restarted on :8080.

### Inferred

- LINE_PREVIEW travel paths (blue/red/black SVG) still flash briefly before beats; distinct from sheet underlay ink.
- Token 2px white stroke is unrelated to retired r≈40 digit masks.

### Unknown / remaining

- Scott visual sign-off on hard-refreshed Play All for 125/127.
