# Active Task

Updated: 2026-09-15 (Stats first)

Branch: `cursor/playbook-jason-clean-slate-ac1f`  
Base: `cursor/dashboard-maxpreps-results-ac1f`

## Dual-machine roles (locked)

Home owns data. School uses Funnel only.

Funnel: https://liberty-coach.tail368a37.ts.net

## Product priority (Scott 2026-09-15)

**AI’s job is counting stats.** Film clip review is coach work later.

North star: a Liberty vs opponent box (PTS, FGM/A, 2PM/A, 3PM/A, FTM/A, REB O/D, AST, STL, BLK, TO) that can be checked against a confirmed scorebook — without Scott walking every AI event. +/− is parked.

**NFHS definitions locked (Scott 2026-09-15, camera notes 2026-09-15 evening):**
- **FT:** lane lined up around the key; technical = one shooter, empty lane. Camera is locked on the key (no pan) during the FT.
- **Assist:** last pass that directly leads to a made field goal; 1–2 dribbles max; no FT assists.
- **TO:** offense loses the ball before a shot. Hudl/Synergy credit whistle TOs by watching the referee (human). Liberty first split: live-ball TO vs dead-ball TO (zoom-out / stoppage). Do not name travel vs charge vs 5-second from vision yet.
- **Steal:** defender’s active play causes that TO (intercept, strip, deflection, held-ball arrow). Not a loose-ball pickup or charge.
- **OREB/DREB:** shooter jersey color vs rebounder jersey color (same = offensive).
- **Block:** ball deflected on the way up / at the peak, near the shooter’s hand; if it still goes in, it is a FG not a block. HS goaltending ignored (almost never called).
- **Paint:** shot from inside the key outline. Camera zooms in during live play, out on dead balls, otherwise pans left–right. Plan: lock the key on zoom-out frames and track that polygon through pan/zoom.
- **Second chance:** same-color rebound after a miss, then a make before the defense possesses.
- **Starters:** coach picks five per team per game; tip-off five is the later fallback. Subs after dead balls.

**Proven:** Starting five is coach-saved per game (`data/lineups/<game_id>.json`, Film Tool + Analysis Results). Box splits STARTERS/BENCH and shows bench points. No schema change.

**Proven (2026-09-15 evening):** NFHS counting rules are now in `stat_rules.py` / `court_memory.py` and wired into the precision event generator + official box.
- FT: lane lined up (or technical = empty lane), camera not panning.
- Assist: made FG, last pass, 1–2 dribble hold, never on FT.
- TO: live vs dead (zoom-out). Steal only if the next player is close to the ball, not a dead-ball pickup.
- OREB/DREB: same team/color when known; else possession touch-chain fallback.
- Block: deflection near the shooter; makes are FGs. HS goaltending ignored.
- Paint / 2nd chance / points off TO: team extras on the box.
These apply to **new** analyses (or a rebuild). The live Adrian run keeps the generator it started with.

**Line score limfac (plain language):** If the spiral book has no Q1–Q4 cells (Adrian), the app cuts the video file into four equal time slices. That is not when the referee ended the period; timeouts and halftime on the tape sit inside those slices. Enter quarter scores in the book to replace the estimate.

**Proven:** One Jr High game emitted 2,699 precision events. Event-level review is not a one-coach workflow across Varsity/JV/boys/girls/Jr High.

**How stats are produced now:** YOLO detections → precision events → Program Mode ledger (Adrian: `adrian_quality` drops high-pass fakes, caps team totals to the book). Scorebook remains the check. Per-player jerseys stay wrong until IDs map.

## Playbook (item 3)

Optimum = imported FastDraw/PDF sheets auto-animate. Scott does **not** trace, rebuild, or write descriptions.

**Proven:** Play All was throwing away extracted polylines (straight digit→digit passes, OCR endpoint snaps) and ignoring Stage-1 session ink until Save. Playback now prefers extract ink, keeps pass/cut midpoints, auto-saves sticky as `auto_extract`.

**Proven (2026-09-15):** Vector extract mapped digits through FastDraw’s white title panel, so 1-Game opening parked 4/5 on the 3-point line. Court crop is the painted outline; Y is piecewise (FT→160, 3pt→235) so elbows sit in the lane. Sheet plays no longer auto-spawn man defenders (looked like every player had the ball). `auto_extract` sticky does not block a fresh extract.

## Jason film stack (item 4)

| Item | Status |
| --- | --- |
| Precision generator + auto-accept 0.85 | Already on |
| E2E suite, migrate/stale scripts, quality docs | Checked out from `origin/main` |
| `src/tracker_wrapper.py` wired into `ai_analyzer.py` | ON by default |
| Undo | Settings → Vision Runtime → uncheck **Jason tracker wrapper** (`ai.tracker_enabled`) |

Ball detector / `ball_confidence` unchanged.

## Clean slate

Wiped analysis outputs from `film_analysis.db` (detections ~55.6M, events ~670k, runs 59, review/provenance/possessions). **Kept** videos, schedule scores, playbook, users.

Re-analyze film from Videos when ready.

## Roster matching (Jr High vs Varsity)

**Proven:** Film Tool defaulted to Varsity, and analysis roster matching fell back across levels. A Jr High game (`jrhigh_adrian_…`) with no `games` row was therefore shown the Varsity film roster. Matching now infers Jr High from the game id, links Adrian to the Jr High schedule, and will not use a Varsity list for a Jr High game.

**Proven:** Confirmed Adrian spiral scorebook now seeds Jr High **Liberty** and a selectable **Adrian** opponent roster (not Home/Away). Analysis roster prefers that confirmed book over a Varsity film list.

## Analysis Results empty after Adrian (Scott 2026-09-16 morning)

**Proven:** The PDF subtitle `jrhigh_adrian%2C_or_…` is a URL-encoding miss, not a missing analysis. The decoded key has ~866k detections and 2,699 events. Videos → Results encodes the comma; Flask left `%2C` in `GAME_ID`; JS encoded again (`%252C`); APIs looked up a key with 0 detections. Starters are coach-picked (not auto-detected); the picker said “No roster yet” because the official box loaded the encoded key.

**Fix:** `normalize_analysis_game_id` unquotes up to 3 times; Analysis Results page + `/api/analysis` + status + starters use it; JS decodes `GAME_ID` on load. Hard refresh after Flask restart.

## Inflated Pos# stats (Scott 2026-09-16)

**Proven:** The 168-shot / 194-point rows were the raw detector tables (Pos # = camera track, not a player). The scorebook named-player helper had been dropping PTS/FG cells, so the official box was filling blanks from 2,699 events. Official box now keeps book PTS/makes as the check. Duplicate jerseys (#11 both teams) use Home = light / Away = dark. Empty REB/AST/STL/BLK/TO/PF and misses come from the 168 accepted film events.

## Live AI progress (all games)

**Proven:** Video Library hid the whole table every poll while a run was going (blink) and only showed a confirm popup. `/api/analysis_jobs` now feeds a site-wide bar (percent, frame n/N, elapsed). Frame text updates about every 500 frames; the bar stays animated so a long game is not mistaken for stuck. Completed stays on the banner ~3 minutes.

## Manual tagging layout (Scott 2026-09-16)

**Proven:** Film Tool tagging is a slim **Tag** strip on the **right edge of the video**. **Off / Def / More** tabs show one group at a time. **Vs** (this game’s opponent) and **5s** (starting fives) stay on the strip while tagging so Game info can stay hidden. Dropdowns sit above the film. Skip / speed controls under the film stay visible while tagging.

**Proven (2026-09-16 afternoon):** The tag card is a compact centered dialog (not full-bleed). Every tag except Start/End QTR uses the same flow: Liberty vs this game’s opponent, then that team’s roster. Jump Ball asks who won. Steal still adds the matching turnover from the other roster. Add-player is an inline field (no nested `prompt()`), so Cancel / Esc / backdrop still close the card. Opponent roster keys off the team you are playing (Adrian on this game), not a generic Opponent list.

## Do not

- Change production `ball_detector.pt` / `ball_confidence` without Scott
- Overwrite home DB from school
- Ask Scott to film-check every AI event
