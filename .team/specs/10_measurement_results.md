# Measurement Results — Unknowns 1–3 (Stage 0 of plan 10 v6)

Date: 2026-10-29
Measured by: Claude Code (playbook coder), on Scott's "Yes, test the 2-3 plays".
Plays tested: 98 (1-Game, 5 steps), 99 (32, 5 steps), 101 (41, 6 steps) — the three largest saved choreographies.

## How it was measured (Proven)

- Code: a clean detached checkout of `team/playbook` at `7c5e90f` (NOT the working copy, which has uncommitted v5 viewer edits), in Claude's scratch folder; removed afterwards.
- Data: DB COPY `C:\Users\scott\Documents\Liberty_Playbook_TestDB\film_analysis_copy.db` (`LIBERTY_DATABASE`). Share tokens `stage0_*` were set on plays 98/99/101 in the COPY only, and cleared again after. The live DB was not opened.
- Uploads folder pointed at an EMPTY scratch folder (`LIBERTY_UPLOAD_FOLDER`), so every sheet image request returned 404.
- Server: `app.run(host='127.0.0.1', port=5055)` (localhost only).
- Browser: headless Chrome driven over the DevTools protocol by a Node 24 script (no new packages). Phone emulation iPhone SE (375×667) and Pixel 7 (412×915), touch on. Load page, wait 6 s, TAP Play All with a real touch event, sample state every 1 s for 25 s, screenshot, then go offline and reload. Every network request was recorded by phase (load / playback / offline).
- court_frac A/B: play 99 rerun with `court_frac` removed from every step (scratch copy only), then the file was restored (hash checked).

## Unknown 1: Choreography-only animation

| Play ID | Choreography-only? | Server endpoints hit during Play All |
|---------|-------------------|--------------------------------------|
| 98      | YES               | `/api/analysis_jobs` poll (13 in 25 s); sheet image GET (404) |
| 99      | YES               | same                                 |
| 101     | YES               | same                                 |

Notes: no `sheet-extract`, `sheet-paths` or `sheet-align` call on load or during Play All on either device. Play All ran (`playAllRunning` true, step advanced 0→1 / 0→3 / 0→2 within 25 s, token positions changed), with every sheet image missing (404) and no console errors. `/api/analysis_jobs` is a background job poller from `base.html`, not playback; it must not be in the static player.

## Unknown 2: Sheet images requested during playback

| Play ID | Sheet images requested? | Which steps / URLs |
|---------|------------------------|--------------------|
| 98      | YES (on load and during playback) | `/play/share/<token>/uploads/bulk_imports/d125…/page_0032.png`, `page_0033.png` |
| 99      | YES | `page_0037.png` … `page_0040.png` |
| 101     | YES | `page_0050.png` … `page_0052.png` |

Notes: the viewer asks for each step's sheet image, but does NOT need it: all returned 404 and the court (SVG), players and movements still drew and animated. So the static build must ship no sheet images, and should stop the viewer from requesting them (a request to a missing file on the player host is harmless but noisy, and the URL leaks the import folder name).

## Unknown 3: Phone layout & offline

| Check | Result | Notes |
|-------|--------|-------|
| iPhone SE layout fits, no horizontal scroll | PASS (no side scroll) / ISSUE | scrollWidth = 375 = window width. But the court starts ~520 of 667 px down: the player must scroll to see the play. |
| Pixel 7 layout fits, no horizontal scroll | PASS / same ISSUE | scrollWidth = 412 = width. Court partly below the fold. |
| Touch playback works (tap Play, step buttons) | PASS | A real touch tap on ▶ Play All (84×40 px) started playback on both devices. |
| Share view includes navbar/sidebar? | YES | `base.html` top bar with logo and ☰ menu. Also editor leftovers in share mode: two "Stop" buttons, Undo, Redo, "Next step", and the text "Use the video button to export a clip". |
| Offline (SW) — page loads | FAIL (expected) | No service worker controls the share page; offline reload shows Chrome's "no internet" page. Stage 2 (PWA) is what adds offline. |
| Offline — playback works | FAIL (expected) | same reason |
| Third-party requests | FOUND | `fonts.googleapis.com` + `fonts.gstatic.com` (Inter font) on every load. Plan says no third-party fetches: the static build must drop or self-host the font. |
| Assets needed for precache | (list) | rendered share page; `/play/share/<t>/choreography` (→ static `plays/<id>/choreography`); the `/static/` CSS/JS the page loads (16 requests on load, 10 of them `/static/`); favicon. Exact list to be taken from the load request log in Stage 1. |

court_frac decision: STRIP. With `court_frac` removed from play 99, the starting token positions were identical on both devices, Play All reached the same step (3) in 25 s, and 18 of 25 samples were pixel-identical (the other 7 differ by ≤13 px, sampled mid-move, consistent with timing). No evidence playback needs it. (Inferred: it is used only when aligning to a sheet image, which the player app will not have.)

## Decision

Proceed to Stage 1, with four adjustments for Scott and Hermes to confirm:
1. Static build removes the `/api/analysis_jobs` poller and the `base.html` navbar/menu.
2. Static build ships no sheet images and stops the viewer requesting them; strip `source_image` (already planned) and `court_frac`.
3. Drop or self-host the Google font (no third-party requests).
4. Phone layout: put the court first (above the buttons) and hide editor-only controls (second Stop, Undo, Redo, export-clip text) in the player build.

Stage 1 does NOT start until Scott confirms.
