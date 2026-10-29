VETTED by Claude Code, 2026-10-29 (v7 revision 3, one binding note): the 4 points are fixed - `{% extends "player_base.html" if player_build else "base.html" %}` with a new templates/player_base.html carrying the same block names (title, head, styles, content, scripts - matches base.html at HEAD); the sheet helper returns null and Stage 1 checks for no /uploads/ request and no self-request; Stage 2 uses static/player/manifest.json and static/player/sw.js, so the main app's static/sw.js and static/manifest.json are untouched; Previous/Next enabled only when player_build. Checked against templates/playbook.html and templates/base.html at HEAD (git show) and git ls-files static.
BINDING NOTE a (section "Sheet image helper", callers list): the plan names the wrong caller. At HEAD the ONLY call is in showStepSourceImage(index) (playbook.html ~line 1121): `const src = sheetImageSrc(step.source_image); ... currentImg.src = src;`. Assigning null to img.src makes the browser request a file named "null", so that branch must test the helper's result and, when it is null, take the existing else branch (removeAttribute('src'), hide the image). There is no showSheetUnderlay caller. The player build also whitelists play_steps columns without source_image, so normally this branch is not reached; the null check is the safety net.

PLAN v7 - Stage 0 measured; Stage 1 NOT BUILT YET

# Jr High Player App — Staged Plan (v7)

**Goal:** A separate PLAYER app for Jr High team. Shows ONLY animated plays Scott picks. Players/parents use on phones. Scott draws/edits in main program; playbook unchanged. Sync ONE-WAY: main → player. Delivery: installable web app (PWA: Add to Home Screen, own icon, full screen, works offline after first load, iPhone/Android, no app store). Publishing: Scott marks plays as "Visible to players" and clicks Publish; app updates next open. Hidden plays are NOT shipped at all (not merely hidden in UI). Privacy: minors — no logins, no names, no analytics, no data collected; plays only; optional team code (soft lock on static host). Target ready: Jan 4, 2027.

**Key existing pieces to reuse:**
- `blueprints/playbook.py`: share routes `/play/share/<token>` and `/play/share/<token>/choreography` are public, no auth
- `playbook_choreography.py`: sticky choreography JSON at `data/playbook/choreography/{play_id}.json`
- Animation: inline SVG/JS in `templates/playbook.html` (lines ~724–7100) and `static/js/playbook-export.js` (video recording)
- Plays table has `team_key` (jh_boys, jh_girls, hs_boys, hs_girls) — already in DB via additive ALTER
- Export: `/playbook/export/<id>` returns play + steps JSON

**Schema decision:** NO schema.sql change. Visibility list kept in a JSON file (`data/playbook/jrhigh_player_visibility.json`). If Scott later wants multi-team or metadata, that becomes a gate.

---

## Stage 0 — Measurement (Unknowns 1–3 on 2–3 Real Plays) — DONE

Stage 0 completed on 2026-10-29. Results: `.team/specs/10_measurement_results.md` (plays 98, 99, 101). Key findings:
- Choreography-only animation: YES (no sheet-extract/sheet-paths/sheet-align calls). `/api/analysis_jobs` poller (13 in 25 s) runs from `base.html` — must be removed from static player.
- Sheet images requested during playback: YES (every step's `/uploads/...` image), but playback works with all 404. Static build ships no sheet images and stops viewer requests; strip `source_image` AND `court_frac` (court_frac decision: STRIP — identical start positions and steps without it).
- Phone layout: court starts ~520 px down (below fold on iPhone SE / Pixel 7). Share view includes `base.html` top bar + menu. Editor leftovers in share mode: two Stop buttons, Undo, Redo, "Next step" button, "Use the video button to export a clip" text.
- Third-party requests: `fonts.googleapis.com` + `fonts.gstatic.com` (Inter font) on every load — must drop or self-host.
- Offline: FAIL (no SW yet — Stage 2 adds it).

Gate: Scott confirmed results. Proceed to Stage 1 with four adjustments below.

---

## Stage 1 — Player App from Share View (Static Build)

**What it does:** Scott sees ALL plays in the main program with a "Visible to players" toggle per play. Clicking "Publish to Player App" builds a static site in `dist/player/` containing ONLY visible plays. Each play becomes a standalone HTML page at `dist/player/plays/<id>/index.html` rendered from `playbook.html` with `view_mode="share"` and a new `player_build=True` flag. The flag makes the template: (a) skip the `base.html` top bar, the `analysis_jobs` poller, and the Google font link; (b) hide editor-only controls and put the court first; (c) make the sheet-image URL helper return `null` so no `/uploads/` request is made. Whitelisted choreography is written as a static JSON file at `plays/<id>/choreography` (no extension). A top-level `dist/player/player.html` lists visible plays and links to each play's page. Testable on Scott's PC by serving `dist/player/` via `python -m http.server` on localhost:8080.

### Files for Stage 1

| File | Action | Purpose |
|------|--------|---------|
| `blueprints/playbook.py` | KEEP existing route `@playbook_bp.route("/playbook/play/<int:play_id>/visibility", methods=["POST"])` | Toggle "Visible to players" for any play (ALL team_keys) |
| `blueprints/playbook.py` | KEEP existing route `@playbook_bp.route("/playbook/publish-player", methods=["POST"])` | Build static player site to `dist/player/` with ONLY visible plays |
| `blueprints/playbook.py` | REPLACE `_build_player_site(db)` | Generate per-play HTML from `playbook.html` with `view_mode="share"` + `player_build=True` + static choreography JSON |
| `templates/playbook.html` | KEEP — Add "Visible to players" toggle switch on every play row; add "Publish to Player App" button | Scott controls visibility per play; one-click publish |
| `templates/playbook.html` | EDIT — Add `player_build` flag checks (see "Template lines the flag touches" below) | Single source of truth for playback; no code duplication |
| `data/playbook/jrhigh_player_visibility.json` | KEEP (empty object `{}`) | Persisted map: `play_id` → `true/false` (visible to players) |
| `templates/player_base.html` | **CREATE new template** | Minimal base for player pages: doctype, head, viewport, system font stack, same block names as `base.html` (title, head, styles, content, scripts), only the CSS/JS links the playback needs, no navbar, no analysis_jobs poller, no Google font, no main-app SW |
| `templates/player_index.html` | CREATE new template | Top-level play list page (standalone, extends `player_base.html`) |
| `dist/player/` | CREATE directory (gitignored) | Output folder for static player site (NOT under `static/`) |
| `static/js/player-viewer.js` | DELETE (v5 viewer, unused) | Remove dead code |
| `templates/player.html` | DELETE (v5 viewer, unused) | Remove dead code |
| `static/css/player.css` | DELETE (v5 viewer, unused) | Remove dead code |
| `scripts/check_animation_sync.py` | DELETE (v5 viewer, unused) | Remove dead code |

### Template lines the `player_build` flag touches (in `templates/playbook.html` at HEAD)

**base.html extension & chrome (replace entirely when `player_build`):**
- Line 1: `{% extends "base.html" %}` → **replace with** `{% extends "player_base.html" if player_build else "base.html" %}`
- The `player_base.html` wrapper provides a complete HTML document with its own `<head>` (viewport meta, system font stack, only the CSS/JS links the playback needs), `<body>`, and the same block names (`title`, `head`, `styles`, `content`, `scripts`) that `playbook.html` fills. No navbar, no `analysis_jobs` poller, no Google Font, no main-app service worker, no manifest link (the player pages inject their own PWA hooks inline).

**playbook.html blocks suppressed when `player_build`:**
- Lines 182–206: `{% if view_mode != "list" %}` page-header block (back link, play title) — suppress
- Lines 211–214: `{% if view_mode == "share" %}` "Shared play" alert — suppress
- Lines 216–232: Progression bar — suppress
- Lines 237–267: Hidden editor toolbar div (already `view_mode != "share"` but suppress entirely)
- Lines 268–286: Control button bar — **keep only**: Play All, Previous (◀), Next (▶), Back (⏮), Play Step (▶ Play step). **Hide**: Add defense, Move them, Undo, Redo, Add picture, Delete picture, Next step (beat-level, `playBeatBtn`).
  - **FIX for point 4:** In `player_build` mode, **enable Previous/Next** (remove the `{% if view_mode == 'share' %}disabled{% endif %}`). These buttons should work for manual step-through in the player app. The template conditional becomes: `{% if view_mode == 'share' and not player_build %}disabled{% endif %}`.
- Lines 287–309: `movementListWrap` (movement editor bar + list) — suppress
- Lines 311–333: `sheetAlignBanner` (alignment status + choreography actions) — suppress
- Lines 387–391: `stepSourceImageWrap` (PDF image under court) — suppress
- Lines 395–398: `stepImages` (collapsed helper list) — suppress
- Lines 401–407: `stepNotes` textarea — suppress
- Lines 410–511: Right panel (Play Details card + step list) — suppress entirely

**Court-first layout (when `player_build`):**
- The main grid `display:grid;grid-template-columns:1fr 300px` (line 233) becomes single-column so the court card is first and full-width. The right panel is already suppressed above.
- Viewport meta: provided by `player_base.html` (`<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">`).

**Font stack (when `player_build`):**
- Lines 517–518 in `head` block: skip the `@import url('https://fonts.googleapis.com/...')` and instead emit a `<style>` block with system font stack: `font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;`

**Sheet image helper (when `player_build`) — FIX for point 2:**
- Lines 755–757: `sheetImageSrc(url)` function — make it return `null` (not `""`) so no `/uploads/` request fires and no `<img src="">` self-request occurs.
- **Callers that must skip setting `src` when `null`:**
  1. `showSheetUnderlay(stepIdx)` — around line 755, calls `sheetImageSrc(steps[stepIdx].source_image)` and sets `img.src`
  2. Any other direct calls to `sheetImageSrc()` in the inline JS
- In the static build, the template receives `shareAssetBase = "."` and `player_build=True`; the helper becomes:
  ```js
  function sheetImageSrc(url) { return null; }
  ```
- Add to Stage 1 check: no request to `/uploads/` AND no image request to the page's own URL (verify in DevTools Network tab).

**Scripts block (when `player_build`):**
- Lines 619–623: Keep the four static script tags (`man_defense.js`, `playbook-taxonomy.js`, `playbook-dnd.js`, `playbook-export.js`) — these are copied to `dist/player/` and referenced with relative paths.
- The inline animation JS (lines 624–7671) is kept in full — this is the **single source of truth** for playback. No code is copied to a separate file.

**PWA hooks (when `player_build`):**
- Inline in rendered HTML (not via `base.html`): `<link rel="manifest" href="manifest.json">` and inline SW registration script (same as `player_index.html`).

### `templates/player_base.html` (NEW — minimal base for player pages)

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
  <title>{% block title %}Liberty Jr High Plays{% endblock %}</title>
  {% block head %}{% endblock %}
  <style>
    /* System font stack — no Google Fonts */
    :root {
      --color-primary:   #01696f;
      --color-primary-d: #015558;
      --color-bg:        #f7f6f2;
      --color-surface:   #ffffff;
      --color-border:    #e2e0da;
      --color-text:      #1a1a1a;
      --color-muted:     #6b7280;
      --radius:          8px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html { -webkit-text-size-adjust: 100%; overflow-x: hidden; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--color-bg);
      color: var(--color-text);
      min-height: 100vh;
      font-size: 16px;
      line-height: 1.45;
      overflow-x: hidden;
      max-width: 100%;
    }
    img, video { max-width: 100%; height: auto; }
  </style>
  {% block styles %}{% endblock %}
  <!-- playbook.css is linked via the styles block in playbook.html -->
</head>
<body>
  {% block content %}{% endblock %}
  {% block scripts %}{% endblock %}
</body>
</html>
```

### `templates/player_index.html` (STANDALONE — extends `player_base.html`)

- Extends `player_base.html`
- No sidebar, no editor toolbar, no save buttons, no main app nav, no Sign In link
- Top bar: "Liberty Jr High Plays" title
- List of visible plays (from `plays` variable): each as a card/link to `plays/<id>/index.html`
- Loads `manifest.json`, registers SW inline
- Uses `playbook.css` (copied to `dist/player/`)
- System font stack (inherited from `player_base.html`)
- Viewport meta (inherited from `player_base.html`)

### New `_build_player_site(db)` — Replacement Implementation

```python
def _build_player_site(db):
    # Load visibility map
    manifest_path = Path(current_app.root_path) / "data" / "playbook" / "jrhigh_player_visibility.json"
    visibility = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    visible_ids = [int(pid) for pid, vis in visibility.items() if vis]

    # Build output directory at repo root (dist/ is gitignored at repo root)
    out_dir = Path(current_app.root_path) / "dist" / "player"
    plays_dir = out_dir / "plays"

    # REBUILD FROM SCRATCH: delete everything, then write only visible plays
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    plays_dir.mkdir(parents=True, exist_ok=True)

    # Copy shared static assets needed by the player template
    static_assets = [
        ("static/js/man_defense.js", "man_defense.js"),
        ("static/js/playbook-taxonomy.js", "playbook-taxonomy.js"),
        ("static/js/playbook-dnd.js", "playbook-dnd.js"),
        ("static/js/playbook-export.js", "playbook-export.js"),
        ("static/css/playbook.css", "playbook.css"),
    ]
    for src_rel, dst_name in static_assets:
        src = Path(current_app.root_path) / src_rel
        dst = out_dir / dst_name
        if src.exists():
            shutil.copy2(src, dst)

    # DO NOT copy main app's manifest.json or sw.js (point 3 fix).
    # Player's own manifest and SW are Stage 2 files (static/player/manifest.json, static/player/sw.js).
    # Icons are copied for the player's own manifest (Stage 2).
    icons_src = Path(current_app.root_path) / "static" / "icons"
    if icons_src.exists():
        shutil.copytree(icons_src, out_dir / "icons", dirs_exist_ok=True)

    # For each visible play: render player template + write whitelisted choreography JSON
    play_list = []
    for pid in visible_ids:
        play = db.execute("SELECT * FROM plays WHERE id = ?", (pid,)).fetchone()
        if not play:
            continue

        # Load steps (whitelisted columns)
        steps = db.execute(
            "SELECT step_number, label, positions_json, movements_json FROM play_steps WHERE play_id = ? ORDER BY step_number",
            (pid,)
        ).fetchall()

        # Load choreography and whitelist (strip source_image and court_frac per Stage 0 decision)
        choreo_path = Path(current_app.root_path) / "data" / "playbook" / "choreography" / f"{pid}.json"
        choreo = json.loads(choreo_path.read_text()) if choreo_path.exists() else {}

        whitelisted_choreo = {}
        if choreo and "steps" in choreo:
            whitelisted_choreo["steps"] = []
            for cstep in choreo["steps"]:
                cstep_data = {
                    "step_index": cstep.get("step_index"),
                    "positions": cstep.get("positions"),
                    "coachOrder": cstep.get("coachOrder"),
                    "movements": cstep.get("movements"),
                    "ink": cstep.get("ink"),
                }
                # court_frac STRIPPED per Stage 0 measurement
                whitelisted_choreo["steps"].append(cstep_data)

        # Create play subdirectory
        play_dir = plays_dir / str(pid)
        play_dir.mkdir(parents=True, exist_ok=True)

        # Write whitelisted choreography as static JSON at the URL the player template fetches
        # player template does: fetch(`${shareAssetBase}/choreography`) with NO .json extension
        # It expects a wrapper: {"ok": true, "sticky": true, "choreography": <doc>}
        # In static build, we set shareAssetBase = "." so fetch("./choreography") hits plays/<id>/choreography
        wrapped_choreo = {
            "ok": True,
            "sticky": True,
            "choreography": whitelisted_choreo
        }
        (play_dir / "choreography").write_text(json.dumps(wrapped_choreo, indent=2))

        # Render playbook.html with view_mode="share" AND player_build=True
        play_dict = dict(play)
        steps_list = [dict(s) for s in steps]
        category_tree = _load_playbook_taxonomy(db)
        team_key = normalize_playbook_team(play_dict.get("team_key"))
        play_html = render_template(
            "playbook.html",
            play=play_dict,
            steps=steps_list,
            category_tree=category_tree,
            team_key=team_key,
            view_mode="share",
            player_build=True,
            editing_play=play_dict,
            editing_steps=steps_list,
            share_token=None,
            share_url=None,
            audience_can_edit=False,
            **_team_template_kwargs(team_key),
        )

        (play_dir / "index.html").write_text(play_html)

        play_list.append({
            "id": play["id"],
            "name": play["name"],
            "category": play["category"],
            "team_key": play["team_key"],
        })

    # Write top-level index page (play selector)
    index_html = render_template("player_index.html", plays=play_list)
    (out_dir / "player.html").write_text(index_html)

    # Write plays index manifest (for the selector)
    (out_dir / "plays_index.json").write_text(json.dumps(play_list, indent=2))

    # Return dist path; caller prints the local URL (point 3 fix)
    return {"ok": True, "count": len(play_list), "path": str(out_dir)}
```

### Precaching list for Stage 2 (exact files the player page loads)

The service worker in Stage 2 must precache exactly these files from `dist/player/`:
- `player.html`
- `playbook.css`
- `man_defense.js`
- `playbook-taxonomy.js`
- `playbook-dnd.js`
- `playbook-export.js`
- `manifest.json` (player's own, created in Stage 2 at `static/player/manifest.json` → copied to `dist/player/`)
- `sw.js` (player's own, created in Stage 2 at `static/player/sw.js` → copied to `dist/player/`)
- `icons/*` (all files under `icons/`)
- `plays_index.json`
- For each visible play: `plays/<id>/index.html` and `plays/<id>/choreography` (runtime cache, not precache)

### Run / Test Commands (Stage 1)

```bash
# 1. Start dev server on a COPY of the real DB (entry point is app.py line 288)
New-Item -ItemType Directory -Force C:\Users\scott\Documents\Liberty_Playbook_TestDB | Out-Null
Copy-Item C:\Users\scott\Documents\liberty-basketball-analysis\film_analysis.db C:\Users\scott\Documents\Liberty_Playbook_TestDB\film_analysis_copy.db
$env:LIBERTY_DATABASE = "C:\Users\scott\Documents\Liberty_Playbook_TestDB\film_analysis_copy.db"
cd C:\Users\scott\Documents\liberty-playbook
& C:\Users\scott\Documents\liberty-basketball-analysis\.venv\Scripts\python.exe app.py

# 2. In browser: open http://localhost:5000/playbook
#    - EVERY play row (all team_keys) shows "Visible to players" toggle
#    - Toggle a few Jr High plays ON, toggle one OFF
#    - Click "Publish to Player App" (button in toolbar)

# 3. Serve the generated static site on localhost (NOT file://):
& C:\Users\scott\Documents\liberty-basketball-analysis\.venv\Scripts\python.exe -m http.server 8080 -d dist\player
#    Open http://localhost:8080/player.html
#    - List shows ONLY the visible plays
#    - Click one → opens plays/<id>/index.html
#    - Court renders FIRST (above controls) with players in correct start spots
#    - Click ▶ Play All → tokens move smoothly along arcs/lines, ball passes animate, holds at each step
#    - Click ◀ Previous / ▶ Next step → step through manually (ENABLED in player build)
#    - Click ⏮ Back → rewinds one action and stops
#    - Click ▶ Play step → plays current step only
#    - No second Stop, no Undo, no Redo, no "Next step" (beat), no export-clip text
#    - No horizontal scroll at 375 px and 412 px wide
#    - Works on mobile Chrome/Safari (test via Chrome DevTools device toolbar)

# 4. Turn a play OFF in main program → click Publish again → refresh http://localhost:8080/player.html → play is GONE (not downloadable)
```

### How Scott Checks by Eye (Stage 1)

1. Go to `/playbook` — ALL plays (any team) show "Visible to players" toggle
2. Toggle ON a Jr High play (e.g., "Horns Entry"), toggle OFF another
3. Click **Publish to Player App** — toast confirms "Player app built: 1 play"
4. Open `http://localhost:8080/player.html` — only the ON play appears in list
5. Click it — court shows FIRST (above controls), 5 offense tokens in correct start spots
6. Click **▶ Play All** — tokens move smoothly along arcs/lines, ball passes animate, holds at each step
7. Click **◀ Previous** — rewinds one step; **▶ Next step** — advances one step; **⏮ Back** — rewinds one action
8. Verify NO second Stop, NO Undo, NO Redo, NO "Next step" (beat), NO "Use the video button to export a clip" text
9. Open Chrome DevTools → Device Toolbar → iPhone SE / Pixel 7 — layout fits, court visible without scroll, touch works, no horizontal scroll
10. In main program: turn the play OFF → click Publish → refresh `player.html` — play is GONE (not in list, `plays/<id>/` deleted)
11. Verify `dist/player/plays/` contains ONLY visible plays; hidden play's folder is removed
12. Zero-visible case: turn ALL plays OFF → click Publish → `dist/player/` rebuilt with empty `plays_index.json`, empty `plays/`, viewer shows empty list (no error)
13. DevTools Network tab: no requests to `fonts.googleapis.com`, `fonts.gstatic.com`, `/api/analysis_jobs`, or `/uploads/...` on load or during playback; no image request to the page's own URL

---

## Stage 2 — PWA: Installable + Offline

**What it adds:** Service worker, manifest, icons, cache-first strategy. After first load, `player.html` and all play pages work offline (no network). "Add to Home Screen" shows custom icon, launches full-screen.

### Files for Stage 2 — FIX for point 3

| File | Action |
|------|--------|
| `static/player/manifest.json` | **CREATE** — PWA manifest (name: "Liberty Jr High Plays", icons, start_url: "player.html", display: standalone) |
| `static/player/sw.js` | **CREATE** — Service worker (cache static assets + player bundles) |
| `static/icons/` | CREATE — icon-192.png, icon-512.png (generated from Liberty logo) |
| `templates/player_index.html` | EDIT — Ensure `<link rel="manifest">`, register SW inline |
| `templates/playbook.html` | VERIFY — Rendered play pages have `<link rel="manifest">` and SW registration (inject in `_build_player_site` if missing) |

**Note:** The `_build_player_site` function copies from `static/player/manifest.json` and `static/player/sw.js` to `dist/player/` (not from `static/manifest.json` or `static/sw.js`). This avoids overwriting the main app's service worker.

### Service Worker Strategy

- **Precache:** `player.html`, `playbook.css`, `man_defense.js`, `playbook-taxonomy.js`, `playbook-dnd.js`, `playbook-export.js`, `manifest.json`, `sw.js`, `icons/*`, `plays_index.json`
- **Runtime cache (cache-first):** `plays/<id>/index.html`, `plays/<id>/choreography` (bundles are static files, cached on first visit)
- **Offline fallback:** cached `player.html` shell shows last-loaded play list

### Run / Test Commands (Stage 2)

```bash
# 1. Restart server
& C:\Users\scott\Documents\liberty-basketball-analysis\.venv\Scripts\python.exe app.py

# 2. Publish from main app (adds SW, manifest, icons to dist/player/)
# 3. Serve locally
& C:\Users\scott\Documents\liberty-basketball-analysis\.venv\Scripts\python.exe -m http.server 8080 -d dist\player
#    Open http://localhost:8080/player.html on the PC in Chrome DevTools mobile view (a phone cannot reach the PC localhost; real phone install is tested after Stage 4 hosting gives https)
#    - Chrome: "Install app" prompt appears / menu → "Add to Home Screen"
#    - iOS Safari: Share → "Add to Home Screen"
# 4. Launch from home screen — full screen, no browser chrome, Liberty icon
# 5. Turn on Airplane mode → reload — play still animates
# 6. Reconnect → SW updates cache silently on next visit
```

### How Scott Checks by Eye (Stage 2)

- Install on iPhone and Android → icon appears, opens full-screen
- Airplane mode → app loads, play animates
- Back online → no error, no double-load

---

## Stage 3 — Publish Button Polish (One-Click from Main Program)

**What it adds:** UX polish. "Publish to Player App" button in main playbook toolbar. Shows count of visible plays. Toast confirms with link to local `http://localhost:8080/player.html`. No separate export step per play.

### Files for Stage 3

| File | Action |
|------|--------|
| `templates/playbook.html` | EDIT — "Publish to Player App" button in toolbar (shows visible count), toast with clickable `http://localhost:8080/player.html` link |
| `static/js/playbook-dnd.js` or inline | ADD — POST to `/playbook/publish-player`, show toast with clickable link |
| `blueprints/playbook.py` | KEEP — Publish route returns `{"ok": True, "count": N, "url": "http://localhost:8080/player.html"}` (caller constructs URL from returned `path`) |

### Run / Test Commands (Stage 3)

```bash
# 1. Restart server
# 2. /playbook → toggle plays ON/OFF → click "Publish to Player App"
# 3. Toast appears: "Player app built: 3 plays" with clickable http://localhost:8080/player.html link
# 4. Click link → dist/player/player.html opens, shows exactly those 3 plays
# 5. Edit a play in main program → click Publish again → dist/player/player.html shows updated animation on refresh
```

### How Scott Checks by Eye (Stage 3)

- One click publishes
- Local `http://localhost:8080/player.html` viewer updates on refresh (no rebuild, no deploy)
- Edit → Publish → viewer shows new version
- Hidden plays stay hidden (not in `dist/player/plays/`)

---

## Stage 4 — Hosting (Free First, Built Locally, Repo Stays Clean)

**Goal:** Scott hosts the player app publicly so players/parents access via URL. No app store. Free tier first. **CRITICAL: The GitHub repo is PUBLIC. Generated bundles must NEVER be committed. Build locally on Scott's PC (where film_analysis.db lives), upload ONLY the built `dist/player/` folder.**

| Option | Cost | Setup | Pros | Cons |
|--------|------|-------|------|------|
| **GitHub Pages** | Free | Push `dist/player/` to `gh-pages` branch via Action | Free HTTPS, custom domain, CDN | Static only. Must pre-generate bundles locally. |
| **Cloudflare Pages** | Free | Connect repo, build command: `python scripts/build_player_site.py` | Free, fast, custom domain | Build runs in cloud — **cannot read film_analysis.db (gitignored)**. Must build locally, push artifact. |
| **Render.com Free Web Service** | Free | `git push` → auto-deploy | Runs Python/Flask, HTTPS | Spins down after 15 min inactivity (cold start ~30s). Not static. |
| **Fly.io** | Free allowance | `fly launch` → deploy | Runs containers, global | Requires Dockerfile, CLI. Not static. |
| **Netlify / Vercel** | Free | Drag-and-drop `dist/player/` or Git integration | Drag-and-drop deploy, HTTPS, CDN | Static only. Drag-and-drop is simplest for Scott. |

**Recommended for Scott (free first): Netlify or Vercel drag-and-drop.**
- Scott runs Publish in main app → `dist/player/` updated locally
- Scott drags `dist/player/` folder to Netlify/Vercel dashboard → live in seconds
- No GitHub Action, no cloud build, no DB in cloud, repo stays clean
- Custom domain: `player.libertybball.com` (or `jh-players.libertybball.com`)

**Alternative (GitHub Pages + Action):** Only if Scott prefers git-based deploy. Action must run on Scott's machine (self-hosted runner) or use a pre-built artifact. Simpler: drag-and-drop.

### Files for Stage 4

| File | Action |
|------|--------|
| `scripts/build_player_site.py` | CREATE — Standalone script: reads LOCAL DB, generates static site to `dist/player/` (same logic as `_build_player_site` but callable from CLI) |
| `dist/player/` | ADD to `.gitignore` (generated, never committed) |
| `data/playbook/jrhigh_player_visibility.json` | ADD to `.gitignore` (Scott's local visibility choices, never committed) |

### Run / Test Commands (Stage 4)

```bash
# Local test of static build (standalone, no Flask)
cd C:\Users\scott\Documents\liberty-playbook
& C:\Users\scott\Documents\liberty-basketball-analysis\.venv\Scripts\python.exe scripts/build_player_site.py
# Serves dist/player/ with: python -m http.server -d dist/player 8080
# Open http://localhost:8080/player.html — works offline, no Python backend

# Deploy: drag dist/player/ folder to Netlify/Vercel dashboard
# Site live at https://<random>.netlify.app/player.html or custom domain
```

### How Scott Checks by Eye (Stage 4)

- Open deployed URL on phone → installs as PWA
- Airplane mode → works
- Click "Publish" in main app → drag `dist/player/` to Netlify → wait 30s → phone shows new play
- Verify public URL shows ONLY visible plays; hidden plays are not in `plays/` folder

---

## Stage 5 — Team Code (Optional Soft Gate, Honest About Static Host)

**What it adds:** Optional 4–6 character code (e.g., "LIBERTY25") to open the player app. **On static hosting, this is a SOFT LOCK only** — anyone with the files can read them (no server to enforce). Code stored in `data/playbook/jrhigh_player_code.json` (Scott sets once). If set, `player_index.html` and play pages show code entry screen; correct code sets a `localStorage` flag and redirects to play list. Wrong code = stay on entry screen. No cookies (static host), no server enforcement.

### Files for Stage 5

| File | Action |
|------|--------|
| `static/js/player-code-gate.js` | CREATE — Checks `localStorage` for `player_code_verified`; if not set and code configured, shows entry modal; verifies against `player_code.json` fetched at runtime |
| `dist/player/player_code.json` | GENERATED at publish — `{"code": "LIBERTY25"}` (only if Scott set a code) |
| `templates/player_index.html` | EDIT — Include `player-code-gate.js`, add code entry modal HTML |
| `templates/playbook.html` | EDIT — Include `player-code-gate.js` and modal into rendered play pages (in `_build_player_site`) |
| `data/playbook/jrhigh_player_code.json` | CREATE — `{"code": "LIBERTY25"}` (Scott sets once, gitignored) |

### Run / Test Commands (Stage 5)

```bash
# 1. Create code file locally
echo '{"code": "LIBERTY25"}' > data/playbook/jrhigh_player_code.json

# 2. Publish from main app → dist/player/player_code.json created
# 3. Open dist/player/player.html → shows "Enter team code" modal
# 4. Enter wrong code → "Invalid code"
# 5. Enter LIBERTY25 → saves localStorage, shows play list
# 6. Close/reopen browser → localStorage remembered, goes straight to plays
# 7. Share URL: /player.html → works (localStorage persists)
# 8. **Honest check:** Open browser DevTools → Application → Local Storage → clear flag → reload → code screen returns. Anyone with file access can read plays/*.json directly.
```

### How Scott Checks by Eye (Stage 5)

- Without code: blocked at entry screen (soft lock)
- With code: full access, persists across sessions via localStorage
- No names, no emails, no analytics — just the code
- **Acknowledged:** On static host, this is a deterrent, not enforcement. If Scott needs real enforcement, Stage 6 = move to a tiny Flask service on Render/Fly (not free long-term).

---

## Summary: Stage Gates

| Stage | Deliverable | Scott Gate |
|-------|-------------|------------|
| 0 | Measurement results for Unknowns 1–3 on 2–3 real plays (`.team/specs/10_measurement_results.md`) | ✅ Scott reviews and confirms |
| 1 | `dist/player/player.html` lists ONLY visible plays; each `plays/<id>/index.html` animates correctly from whitelisted choreography (served on localhost:8080) | ✅ Eye-check: play animates correctly; hidden plays absent from `dist/player/plays/`; zero-visible case works; no base.html chrome, no poller, no sheet images, no Google font, court first, editor controls hidden |
| 2 | PWA installs, works offline | ✅ Eye-check: home screen icon, airplane mode works |
| 3 | One-click Publish from playbook toolbar | ✅ Eye-click: button shows count, toast confirms, `http://localhost:8080/player.html` link opens correct plays |
| 4 | Public URL (free hosting, drag-and-drop) | ✅ Eye-check: deployed URL works on phone, installs, shows only visible plays |
| 5 | Optional team code (soft lock) | ✅ Eye-check: code gate works, no PII collected, honest about static-host limits |

---

## Notes for Coder (Claude Code)

- **Reuse the share view logic, not the template:** The player app is built by rendering `playbook.html` with `view_mode="share"` and `player_build=True`. Do not copy animation code into a separate `player-viewer.js`. The share view already uses the exact same animation engine as the main program; `player_build` flag strips chrome and keeps the playback code identical.
- **Static choreography JSON:** Write whitelisted choreography to `plays/<id>/choreography` (NO .json extension). The player template's `loadStickyChoreographyDoc()` fetches `${shareAssetBase}/choreography`; in the static build, `shareAssetBase = "."` so it fetches `./choreography`. The file must be wrapped as `{"ok": true, "sticky": true, "choreography": <doc>}`. python http.server serves unknown extensions as application/octet-stream; fetch().json() still parses it.
- **No schema changes:** Use JSON files (`jrhigh_player_visibility.json`, `jrhigh_player_code.json`). If coder thinks a column is needed, stop and ask Scott.
- **Privacy:** Bundles omit `source_image`, `notes`, `court_frac`. Whitelist fields in choreography per step. No `analytics.js`, no `fetch` to third parties, no cookies (localStorage only for code gate).
- **Static output:** Stage 4 build script (`scripts/build_player_site.py`) runs against Scott's LOCAL DB — no runtime DB on static host. `dist/player/` and visibility/code JSON files are gitignored.
- **Public repo:** Generated bundles NEVER committed. `dist/player/` and `data/playbook/jrhigh_player_*.json` in `.gitignore`.
- **Run command:** Entry point is `& C:\Users\scott\Documents\liberty-basketball-analysis\.venv\Scripts\python.exe app.py` (app.py line 288). Use this in all test commands.
- **Testing:** Each stage has explicit "How Scott checks by eye" — coder must verify these before calling stage done.
- **Standalone pages:** Rendered play pages are complete HTML documents (no `base.html` extension). The top-level `player.html` is a standalone template (`player_index.html`) that extends `player_base.html` (not `base.html`).
- **Stage 1 test uses localhost, not file://:** `python -m http.server 8080 -d dist/player` — browsers block fetch() and SW on file://.
- **Path fix:** `dist/` is at repo root (gitignored), not outside the repo. Use `Path(current_app.root_path) / "dist" / "player"`.
- **Rebuild from scratch:** `_build_player_site` deletes `dist/player/` entirely before writing, so hidden plays are gone and zero-visible case is clean.
- **Column names:** `play_steps` uses `step_number`, `positions_json`, `movements_json` (schema.sql). Choreography whitelist applied PER STEP inside `choreography.steps[]` — top-level choreography has no positions/movements/ball.
- **Database for testing:** The liberty-playbook worktree has NO film_analysis.db. Use `C:\Users\scott\Documents\liberty-basketball-analysis\.venv\Scripts\python.exe` and set `LIBERTY_DATABASE` to a COPY of the real DB placed OUTSIDE the repo (C:\Users\scott\Documents\Liberty_Playbook_TestDB; a copy inside the worktree is not gitignored and the repo is public) (never the live DB from a dev branch).
- **Live film_analysis.db opened read-only only; tests use tmp_path copies only.** Do not edit any other file, do not create scratch files in the repo.

---

## Binding Checker Notes (from v6, folded into body)

(a) The temp Flask app uses the REAL templates folder and registers the playbook blueprint, while root_path, data and dist stay under tmp_path.
(b) The temp DB holds every table the share render reads.
(c) The court_frac assertion follows the Stage 0 decision (STRIP).
(d) Stage 0 has run; its results are in `.team/specs/10_measurement_results.md`. Stage 1 starts now.

---

## Acceptance Tests (pytest)

### `tests/test_player_publish.py`

```python
import json
import pytest
import sqlite3
from pathlib import Path

# Fixtures: tmp_path provided by pytest
# This test creates its OWN temp DB and temp root under tmp_path.
# It writes NOTHING outside tmp_path.

def test_build_player_site_excludes_hidden_plays(tmp_path):
    """_build_player_site writes only visible plays; hidden plays absent from dist/player/plays/."""
    from blueprints.playbook import _build_player_site
    from playbook_choreography import save_choreography
    from flask import Flask

    # 1. Create a temp Flask app with its root_path = tmp_path
    app = Flask(__name__, root_path=str(tmp_path))
    app.config['TESTING'] = True

    # 2. Create temp DB under tmp_path
    db_path = tmp_path / "test.db"
    app.config['DATABASE'] = str(db_path)
    app.config['LIBERTY_DATABASE'] = str(db_path)

    # 3. Init schema in temp DB (mirror real schema for plays, play_steps, shares)
    with app.app_context():
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE plays (
                id INTEGER PRIMARY KEY,
                name TEXT, category TEXT, team_key TEXT, category_id INTEGER
            );
            CREATE TABLE play_steps (
                id INTEGER PRIMARY KEY,
                play_id INTEGER, step_number INTEGER, label TEXT,
                positions_json TEXT, movements_json TEXT
            );
            CREATE TABLE shares (
                id INTEGER PRIMARY KEY,
                play_id INTEGER, token TEXT, expires_at TEXT
            );
        """)
        conn.commit()
        conn.close()

    # 4. Create test data in temp DB
    with app.app_context():
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO plays (id, name, category, team_key, category_id) VALUES (1, 'Visible Play', 'Offense', 'jh_boys', 1)")
        conn.execute("INSERT INTO plays (id, name, category, team_key, category_id) VALUES (2, 'Hidden Play', 'Offense', 'jh_boys', 1)")
        conn.execute("INSERT INTO play_steps (play_id, step_number, label, positions_json, movements_json) VALUES (1, 1, 'Start', '{}', '[]')")
        conn.execute("INSERT INTO play_steps (play_id, step_number, label, positions_json, movements_json) VALUES (2, 1, 'Start', '{}', '[]')")
        conn.commit()
        conn.close()

    # 5. Create temp choreography dir and save choreography for play 1
    #    (with private fields that must be stripped)
    with app.app_context():
        choreo_dir = tmp_path / "data" / "playbook" / "choreography"
        choreo_dir.mkdir(parents=True, exist_ok=True)
        save_choreography(1, {
            "steps": [{
                "step_index": 0,
                "source_image": "/uploads/secret.pdf",  # must be stripped
                "court_frac": 0.5,                      # stripped per Stage 0 decision
                "positions": {"o1": {"x": 100, "y": 200}},
                "coachOrder": True,
                "movements": [{"type": "cut", "player": "o1", "to": {"x": 150, "y": 250}}],
                "ink": {"paths": {}, "marks": {}, "passes": [], "actions": []},
            }]
        }, base=choreo_dir)

    # 6. Create visibility manifest under tmp_path
    manifest_dir = tmp_path / "data" / "playbook"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / "jrhigh_player_visibility.json"
    manifest_path.write_text(json.dumps({"1": True, "2": False}))

    # 7. Run _build_player_site with the temp app context
    with app.app_context():
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        result = _build_player_site(db)

    # Assertions
    assert result["ok"] is True
    assert result["count"] == 1

    out_dir = tmp_path / "dist" / "player"
    plays_dir = out_dir / "plays"

    # Hidden play NOT shipped
    assert not (plays_dir / "2").exists(), "Hidden play 2 must not exist in output"
    assert (plays_dir / "1").exists(), "Visible play 1 must exist in output"

    # plays_index.json contains only play 1
    index = json.loads((out_dir / "plays_index.json").read_text())
    assert len(index) == 1
    assert index[0]["id"] == 1

    # Play 1 bundle: HTML exists (check via string presence, not JSON parse)
    play_html = (plays_dir / "1" / "index.html").read_text()
    assert "Visible Play" in play_html
    assert "shareAssetBase" in play_html
    assert 'const shareAssetBase = ".";' in play_html
    # Verify static paths rewritten to relative
    assert 'href="/static/' not in play_html
    assert 'src="/static/' not in play_html
    assert 'href="./' in play_html or 'src="./' in play_html

    # Choreography file (NO .json extension) with wrapper
    choreo = json.loads((plays_dir / "1" / "choreography").read_text())
    assert choreo["ok"] is True
    assert choreo["sticky"] is True
    assert "steps" in choreo["choreography"]
    cstep = choreo["choreography"]["steps"][0]
    assert "source_image" not in cstep
    assert "court_frac" not in cstep
    assert "positions" in cstep
    assert "coachOrder" in cstep
    assert "movements" in cstep
    assert "ink" in cstep

def test_build_player_site_zero_visible(tmp_path):
    """Zero visible plays → empty plays_index.json, empty plays/ dir, no error."""
    from blueprints.playbook import _build_player_site
    from flask import Flask
    import sqlite3

    # Create temp app and DB under tmp_path (same pattern as above)
    app = Flask(__name__, root_path=str(tmp_path))
    app.config['TESTING'] = True
    db_path = tmp_path / "test.db"
    app.config['DATABASE'] = str(db_path)
    app.config['LIBERTY_DATABASE'] = str(db_path)

    with app.app_context():
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE plays (id INTEGER PRIMARY KEY, name TEXT, category TEXT, team_key TEXT, category_id INTEGER);
            CREATE TABLE play_steps (id INTEGER PRIMARY KEY, play_id INTEGER, step_number INTEGER, label TEXT, positions_json TEXT, movements_json TEXT);
            CREATE TABLE shares (id INTEGER PRIMARY KEY, play_id INTEGER, token TEXT, expires_at TEXT);
        """)
        conn.commit()
        conn.close()

    manifest_dir = tmp_path / "data" / "playbook"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "jrhigh_player_visibility.json").write_text(json.dumps({"1": False}))

    with app.app_context():
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        result = _build_player_site(db)

    assert result["ok"] is True
    assert result["count"] == 0

    out_dir = tmp_path / "dist" / "player"
    assert (out_dir / "plays_index.json").exists()
    index = json.loads((out_dir / "plays_index.json").read_text())
    assert index == []
    assert (out_dir / "player.html").exists()
```

### Run Tests

```bash
cd C:\Users\scott\Documents\liberty-playbook
& C:\Users\scott\Documents\liberty-basketball-analysis\.venv\Scripts\python.exe -m pytest tests/test_player_publish.py -v
```

---

## Measurement Results Reference (`.team/specs/10_measurement_results.md`)

Stage 0 completed 2026-10-29. Full results in that file. Summary:

**Unknown 1 — Choreography-only animation:**
- Play 98: YES (endpoints: `/api/analysis_jobs` poll 13×, sheet image GET 404)
- Play 99: YES (same)
- Play 101: YES (same)
- No `sheet-extract`, `sheet-paths`, `sheet-align` calls.

**Unknown 2 — Sheet images requested:**
- Play 98: YES (all steps, `/uploads/.../page_0032.png` etc.)
- Play 99: YES (all steps)
- Play 101: YES (all steps)
- All 404; playback unaffected. Strip `source_image` and `court_frac`.

**Unknown 3 — Phone layout & offline:**
- iPhone SE (375×667): PASS no horizontal scroll; court starts ~520 px down (below fold)
- Pixel 7 (412×915): PASS no horizontal scroll; court partly below fold
- Touch playback: PASS
- Share view includes navbar/sidebar: YES (base.html top bar + menu)
- Editor leftovers in share mode: two Stop, Undo, Redo, "Next step", export-clip text
- Offline: FAIL (no SW — Stage 2)
- Third-party: `fonts.googleapis.com` + `fonts.gstatic.com` (Inter font)
- court_frac decision: STRIP (A/B test on play 99 showed identical start positions and steps)