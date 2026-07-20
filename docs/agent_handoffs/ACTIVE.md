# Active Task

Updated: 2026-07-20
Branch: `cursor/film-tool-reports-fix-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | film-tool-video-team-ux |
| **status** | `completed` |
| **assigned_to** | cursor-cloud-agent |

## Report

### Proven

- **Video file:** `uploads/nfhs_gam30b09cbb4f.mp4` exists (~4.9GB). `videos.id=8` → `file_path` same; `stored_filename=nfhs_gam30b09cbb4f.mp4`; opponent Wilder. HTTP `/uploads/...` → 200/206, `Accept-Ranges: bytes`, moov at offset 36 (fast-start).
- **Tags:** `film_tool_games` `game-1784304093435` has `analysis_key=…__rerun_20260718_215754`, **71** tags. Film page injects `FILM_TOOL_UPLOADED_VIDEO_URL`, `CLIENT_GAME_ID`, `GAME_ID`, opponent.
- **Root cause (black film UX):** Server already set `video.src`, but (1) Focus mode removes native controls so chrome looks “stuck” at 0:00 until Play; (2) loading saved tags said “Reload video…” and did not re-assert hosted src; (3) Manual Report link previously opened `/film?tab=reports` **without** filename (no video). Hardened auto-load + preload + first-frame nudge + re-load after deep-link.
- **Root cause (team “Select”):** Quick-tag stores team as **Liberty** / opponent name, but row dropdown vocabulary was only `Our Team` / `Opponent` — no match → blank **Select**, and later saves wiped team to `""`. Fixed: sync vocabulary to live names, map Liberty↔Our Team, default action tags to Liberty, clearer Team prompt.
- **Commit:** `cf9197e` — Fix Film Tool video auto-load and Liberty team dropdown. Pushed to `origin/cursor/film-tool-reports-fix-ac1f`. Tests: 11 passed.

### Inferred

- Large MP4 may still show black briefly until first frame buffers; Play in the focus dock should paint video.

### Unknown

- Whether Scott’s browser still has a stale cached `film-tool.js` (hard-refresh if so). Cache bust is now `?v=20260720filmVideoTeam`.

### Click paths (Scott)

**Open Wilder with video + 71 tags**
1. Nav → **Videos**
2. Row for Wilder / `nfhs_gam30b09cbb4f` → **Film Tool** (not bare nav “Film Tool”)
3. Expect Focus mode, status “Loaded … + video”, score from tags, Tagged events table with 71 rows
4. Press **Play** (or dock ▶) if the frame is still black at 0:00

**Set team on each tag**
1. Click an event button (e.g. **2PT Make**)
2. Dialog: **Team — who did this action?** → click **Liberty** (primary) or opponent name
3. Then pick player (if required)
4. Or edit the **Team** column in Tagged events (dropdown now lists Liberty / opponent; blank “— Team —” is not the default for action tags)

### Changes

- `static/js/film-tool.js` — `syncTeamVocabulary`, `resolveTeamSelectValue`, `ensureHostedVideoLoaded`, clearer quick-tag Team UI
- `templates/film_tool.html` — preload=auto; cache bust `20260720filmVideoTeam`
- `templates/videos.html` — Manual Report includes `/film/<filename>`
- `blueprints/core.py` — build-info cache bust string
- tests updated
