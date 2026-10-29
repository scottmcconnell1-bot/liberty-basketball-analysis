VETTED by Claude Code (plan checker), 2026-10-28 (v6 v2; stamp reworded 21:55 after two Muse DISAGREEs on wording). NOTHING IN THIS PLAN HAS BEEN BUILT OR MEASURED YET. What the checker verified is the PLAN TEXT: it now SAYS TO (1) write each play's data as plays/<id>/choreography (no extension) wrapped as {"ok","sticky","choreography"}, matching templates/playbook.html lines 3579-3589 (no "choreography.json" left; checked by search of the whole file); (2) rewrite /static/ links to relative paths and measure base.html's chrome and assets in Stage 0; (3) decide court_frac in Stage 0; (4) build tests that create their own Flask app, temp DB and temp root under tmp_path and write nothing outside it; (5) have the coder run Stage 0 later by code reading plus a headless check on the DB COPY with a token created only there; (6) delete the v5 viewer files in Stage 1; (7) name Claude Code as coder. BINDING CHECKER NOTES for the coder: (a) the temp Flask app uses the REAL templates folder and registers the playbook blueprint, while root_path, data and dist stay under tmp_path; (b) the temp DB holds every table the share render reads; (c) the court_frac assertion follows the Stage 0 decision; (d) Stage 0 has NOT run; when it runs, its results go in a NEW file .team/specs/10_measurement_results.md, and Stage 1 does not start until Scott confirms them. Previous rejection: 10_jrhigh_player_app_plan_v6_v1_REJECTED.md.

# Jr High Player App — Staged Plan (v6)

**Goal:** A separate PLAYER app for Jr High team. Shows ONLY animated plays Scott picks. Players/parents use on phones. Scott draws/edits in main program; playbook unchanged. Sync ONE-WAY: main → player. Delivery: installable web app (PWA: Add to Home Screen, own icon, full screen, works offline after first load, iPhone/Android, no app store). Publishing: Scott marks plays as "Visible to players" and clicks Publish; app updates next open. Hidden plays are NOT shipped at all (not merely hidden in UI). Privacy: minors — no logins, no names, no analytics, no data collected; plays only; optional team code (soft lock on static host). Target ready: Jan 4, 2027.

**Key existing pieces to reuse:**
- `blueprints/playbook.py`: share routes `/play/share/<token>` and `/play/share/<token>/choreography` are public, no auth
- `playbook_choreography.py`: sticky choreography JSON at `data/playbook/choreography/{play_id}.json`
- Animation: inline SVG/JS in `templates/playbook.html` (lines ~724–7100) and `static/js/playbook-export.js` (video recording)
- Plays table has `team_key` (jh_boys, jh_girls, hs_boys, hs_girls) — already in DB via additive ALTER
- Export: `/playbook/export/<id>` returns play + steps JSON

**Schema decision:** NO schema.sql change. Visibility list kept in a JSON file (`data/playbook/jrhigh_player_visibility.json`). If Scott later wants multi-team or metadata, that becomes a gate.

---

## Stage 0 — Measurement (Unknowns 1–3 on 2–3 Real Plays) — DO FIRST

Before any build, measure the three unknowns on 2–3 real plays that have saved choreography. This prevents rework.

### Unknown 1: Does every visible play animate from its saved choreography alone (no POST to sheet-extract/sheet-paths)?

**What to measure:**
- Pick 2–3 plays that HAVE saved choreography (`data/playbook/choreography/<id>.json` exists and has `steps` with `positions`, `coachOrder`, `movements`, `ink`).
- Open the share view for each: `http://localhost:5000/play/share/<token>` (or the share route that renders `playbook.html` with `view_mode="share"`).
- In browser DevTools Network tab, filter to XHR/fetch. Click **Play All**.
- Record: any POST to `/sheet-extract`, `/sheet-paths`, `/sheet-align`? Any fetch of `/uploads/...` sheet images?
- If NO server calls during playback → choreography alone is sufficient.
- If YES server calls → those plays need their paths baked at Publish time (or excluded from Publish).

**Acceptance:** Document per play: "choreography-only: YES/NO", list any server endpoints hit.

### Unknown 2: Privacy — does the share view request sheet images during playback of a choreographed play?

**What to measure:**
- Same 2–3 plays. In DevTools Network tab, filter to "Img" or search for `/uploads/`.
- Click **Play All** and step through.
- Record: any sheet image (`/uploads/...`) requested during playback?
- If YES → the static player build must NOT include those sheet URLs, and the viewer must not try to fetch them.
- Check `sheetImageSrc()` in `playbook.html` (line ~795): it prefixes with `shareAssetBase` when `shareAssetBase` is set. In the static build, `shareAssetBase` will point to the local static folder (which has no `/uploads/`). The viewer must gracefully handle missing sheet images (already the case if `sheetImageSrc` returns a broken URL — but we must verify no fetch is attempted).

**Acceptance:** Document per play: "sheet images requested during playback: YES/NO", and if YES, which steps.

### Unknown 3: Does the share page work on a phone (layout, touch, size) and offline as a PWA?

**What to measure:**
- Open the share view in Chrome DevTools Device Toolbar (iPhone SE, Pixel 7).
- Check: court fits, no horizontal scroll, playback controls reachable, touch works (tap to play, swipe not required).
- Check: does the page extend `base.html` (navbar, sidebar)? In share mode (`view_mode="share"`), what chrome is rendered?
- Simulate offline: DevTools → Application → Service Workers → Offline checkbox. Reload. Does the page load? Does playback work?
- List assets that would need to be precached: `playbook.html` (the rendered share page), `playbook.css`, inline JS, `man_defense.js`, `playbook-taxonomy.js`, `playbook-dnd.js`, `playbook-export.js`, icons, manifest.
- **court_frac decision:** `applyStickyChoreographyDoc` (playbook.html line 3601) reads `match.court_frac`. Determine if playback needs it — if yes, keep it in whitelisted choreography (it is a number, not private); if no, strip it.

**Acceptance:** Screenshot or notes: "phone layout OK / issues: ...", "offline: works / fails because: ...", list of assets to precache, court_frac decision (keep/strip).

### How to run the measurement (WHO and HOW, without human DevTools where possible)

**WHO measures:** The coder (Claude Code) reads the playback code paths in `templates/playbook.html` for `fetch`/`img` calls and runs a headless check where possible.

**HOW:**
- For Unknowns 1 & 2: Search `playbook.html` for `fetch(`, `XMLHttpRequest`, `sheetImageSrc`, `sheetApiUrl`, `/uploads/`, `/sheet-extract`, `/sheet-paths`, `/sheet-align`. Trace each call path to confirm whether it executes during playback of a choreographed play. Run a headless Playwright/Puppeteer script against the share view on the DB COPY to automate network capture.
- For Unknown 3: Inspect the rendered share-view HTML for `base.html` chrome (navbar, sidebar) and viewport meta. The coder evaluates layout from the template structure; phone/offline check can use headless mobile emulation.
- **Share token:** Must be created in the DB COPY only (insert into `shares` table or use the share route on the copy). Never use a production token.

```bash
# 1. Start dev server on a COPY of the real DB
New-Item -ItemType Directory -Force C:\Users\scott\Documents\Liberty_Playbook_TestDB | Out-Null
Copy-Item C:\Users\scott\Documents\liberty-basketball-analysis\film_analysis.db C:\Users\scott\Documents\Liberty_Playbook_TestDB\film_analysis_copy.db
$env:LIBERTY_DATABASE = "C:\Users\scott\Documents\Liberty_Playbook_TestDB\film_analysis_copy.db"
cd C:\Users\scott\Documents\liberty-playbook
& C:\Users\scott\Documents\liberty-basketball-analysis\.venv\Scripts\python.exe app.py

# 2. Find 2-3 plays with saved choreography
#    In browser: http://localhost:5000/playbook
#    Note play IDs that have choreography files: data/playbook/choreography/<id>.json

# 3. Get share tokens for those plays FROM THE DB COPY ONLY
#    For each play ID, visit http://localhost:5000/play/share/<token> (or the route that renders view_mode="share")

# 4. Measure Unknowns 1-3:
#    - Unknowns 1 & 2: Coder reads code paths + runs headless network capture (Playwright) against the share view
#    - Unknown 3: Coder inspects template for base.html chrome + headless mobile emulation
# 5. Record results in a Markdown file: .team/specs/10_measurement_results.md
```

**Gate:** Do not proceed to Stage 1 until measurement results are written and Scott confirms.

---

## Stage 1 — Player App from Share View (Static Build)

**What it does:** Scott sees ALL plays in the main program with a "Visible to players" toggle per play. Clicking "Publish to Player App" builds a static site in `dist/player/` containing ONLY visible plays. Each play becomes a standalone HTML page at `dist/player/plays/<id>/index.html` rendered from the share view template (`playbook.html` with `view_mode="share"`), with its whitelisted choreography written as a static JSON file at `plays/<id>/choreography`. A top-level `dist/player/player.html` lists visible plays and links to each play's page. Testable on Scott's PC by serving `dist/player/` via `python -m http.server` on localhost:8080.

### Files for Stage 1

| File | Action | Purpose |
|------|--------|---------|
| `blueprints/playbook.py` | KEEP existing route `@playbook_bp.route("/playbook/play/<int:play_id>/visibility", methods=["POST"])` | Toggle "Visible to players" for any play (ALL team_keys) |
| `blueprints/playbook.py` | KEEP existing route `@playbook_bp.route("/playbook/publish-player", methods=["POST"])` | Build static player site to `dist/player/` with ONLY visible plays |
| `blueprints/playbook.py` | REPLACE `_build_player_site(db)` | Generate per-play HTML from share template + static choreography JSON |
| `templates/playbook.html` | KEEP — Add "Visible to players" toggle switch on every play row; add "Publish to Player App" button | Scott controls visibility per play; one-click publish |
| `data/playbook/jrhigh_player_visibility.json` | KEEP (empty object `{}`) | Persisted map: `play_id` → `true/false` (visible to players) |
| `templates/player_index.html` | CREATE new template | Top-level play list page (standalone, no `base.html`) |
| `dist/player/` | CREATE directory (gitignored) | Output folder for static player site (NOT under `static/`) |
| `static/js/player-viewer.js` | DELETE (v5 viewer, unused) | Remove dead code |
| `templates/player.html` | DELETE (v5 viewer, unused) | Remove dead code |
| `static/css/player.css` | DELETE (v5 viewer, unused) | Remove dead code |
| `scripts/check_animation_sync.py` | DELETE (v5 viewer, unused) | Remove dead code |

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

    # Copy shared static assets needed by the share-view-based pages
    # These are the JS/CSS files the share view already uses
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

    # Copy icons and PWA files
    for asset in ["manifest.json", "sw.js"]:
        src = Path(current_app.root_path) / "static" / asset
        dst = out_dir / asset
        if src.exists():
            shutil.copy2(src, dst)
    icons_src = Path(current_app.root_path) / "static" / "icons"
    if icons_src.exists():
        shutil.copytree(icons_src, out_dir / "icons", dirs_exist_ok=True)

    # For each visible play: render share-view HTML + write whitelisted choreography JSON
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

        # Load choreography and whitelist (strip source_image, notes; court_frac decision from Stage 0)
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
                # court_frac: keep ONLY if Stage 0 measurement decided playback needs it (it's a number, not private)
                # if court_frac_needed:
                #     cstep_data["court_frac"] = cstep.get("court_frac")
                whitelisted_choreo["steps"].append(cstep_data)

        # Create play subdirectory
        play_dir = plays_dir / str(pid)
        play_dir.mkdir(parents=True, exist_ok=True)

        # Write whitelisted choreography as static JSON at the URL the share view fetches
        # share view does: fetch(`${shareAssetBase}/choreography`) with NO .json extension (playbook.html line 3582)
        # It expects a wrapper: {"ok": true, "sticky": true, "choreography": <doc>}
        # In static build, we set shareAssetBase = "." so fetch("./choreography") hits plays/<id>/choreography (no extension)
        # python http.server serves unknown extensions as application/octet-stream; fetch().json() still parses it.
        wrapped_choreo = {
            "ok": True,
            "sticky": True,
            "choreography": whitelisted_choreo
        }
        (play_dir / "choreography").write_text(json.dumps(wrapped_choreo, indent=2))

        # Render the share-view HTML for this play
        # We call render_template with view_mode="share", and inject shareAssetBase="." so fetches are relative
        play_dict = dict(play)
        steps_list = [dict(s) for s in steps]
        category_tree = _load_playbook_taxonomy(db)
        team_key = normalize_playbook_team(play_dict.get("team_key"))
        play_html = render_template(
            "playbook.html",
            plays=[],
            playbooks=[],
            categories=PLAYBOOK_CATEGORIES,
            category_tree=category_tree,
            editing_play=play_dict,
            editing_steps=steps_list,
            view_mode="share",
            selected_category_id=play_dict["category_id"],
            share_url=None,
            share_token=None,  # This makes shareAssetBase = null in template; we'll override in rendered HTML
            **_team_template_kwargs(team_key),
        )

        # Post-process the rendered HTML:
        # 1. Replace `const shareAssetBase = null;` with `const shareAssetBase = ".";`
        # 2. Rewrite absolute /static/... URLs to relative paths (since dist/player/ has no /static/ prefix)
        #    playbook.html uses url_for('static', ...) in head (line 527) and scripts (lines 629-632)
        #    base.html (extended at line 1) also injects its own CSS/JS via url_for('static', ...)
        #    We must capture base.html's CSS/JS and inline or copy them, then strip the base.html chrome.
        # 3. Strip base.html chrome (navbar, sidebar, sign-in link) — share view still extends base.html
        #    The share view omits editor UI when view_mode="share" but keeps the layout wrapper.
        #    Strategy: render with a flag `player_build=True` that skips base.html extension, or post-process.
        #    Here we post-process: remove everything outside <body> content we need, keep only the share-view court/controls.
        # 4. Ensure <link rel="manifest" href="manifest.json"> and SW registration are present (inject if missing).
        play_html = play_html.replace(
            'const shareAssetBase = null;',
            'const shareAssetBase = ".";'
        )
        # Rewrite /static/... -> relative (./...)
        play_html = play_html.replace('href="/static/', 'href="./')
        play_html = play_html.replace('src="/static/', 'src="./')
        # Also rewrite any url_for('static', ...) that rendered as /static/...
        # Note: base.html's CSS/JS must be measured in Stage 0 and copied to dist/player/
        # If base.html injects critical CSS/JS not in our static_assets list, add them there.

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

    return {"ok": True, "count": len(play_list), "url": "http://localhost:8080/player.html"}
```

### `templates/player_index.html` (STANDALONE — does NOT extend base.html)

- Complete HTML document: `<!DOCTYPE html>`, `<html>`, `<head>`, `<body>`
- No sidebar, no editor toolbar, no save buttons, no main app nav, no Sign In link
- Top bar: "Liberty Jr High Plays" title
- List of visible plays (from `plays` variable): each as a card/link to `plays/<id>/index.html`
- Loads `manifest.json`, registers SW inline
- Minimal CSS (can inline or use `playbook.css`)

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
#    - Court renders with players in correct start spots
#    - Click ▶ Play All → tokens move smoothly along arcs/lines, ball passes animate, holds at each step
#    - Click ◀ Back / ▶ Next step → step through manually
#    - Works on mobile Chrome/Safari (test via Chrome DevTools device toolbar)

# 4. Turn a play OFF in main program → click Publish again → refresh http://localhost:8080/player.html → play is GONE (not downloadable)
```

### How Scott Checks by Eye (Stage 1)

1. Go to `/playbook` — ALL plays (any team) show "Visible to players" toggle
2. Toggle ON a Jr High play (e.g., "Horns Entry"), toggle OFF another
3. Click **Publish to Player App** — toast confirms "Player app built: 1 play"
4. Open `http://localhost:8080/player.html` — only the ON play appears in list
5. Click it — court shows 5 offense tokens in correct start spots
6. Click **▶ Play All** — tokens move smoothly along arcs/lines, ball passes animate, holds at each step
7. Click **◀ Back** — rewinds one action; **▶ Next step** — advances one action
8. Open Chrome DevTools → Device Toolbar → iPhone SE / Pixel 7 — layout fits, touch works, no horizontal scroll
9. In main program: turn the play OFF → click Publish → refresh `player.html` — play is GONE (not in list, `plays/<id>/` deleted)
10. Verify `dist/player/plays/` contains ONLY visible plays; hidden play's folder is removed
11. Zero-visible case: turn ALL plays OFF → click Publish → `dist/player/` rebuilt with empty `plays_index.json`, empty `plays/`, viewer shows empty list (no error)

---

## Stage 2 — PWA: Installable + Offline

**What it adds:** Service worker, manifest, icons, cache-first strategy. After first load, `player.html` and all play pages work offline (no network). "Add to Home Screen" shows custom icon, launches full-screen.

### Files for Stage 2

| File | Action |
|------|--------|
| `static/manifest.json` | CREATE — PWA manifest (name: "Liberty Jr High Plays", icons, start_url: "player.html", display: standalone) |
| `static/sw.js` | CREATE — Service worker (cache static assets + player bundles) |
| `static/icons/` | CREATE — icon-192.png, icon-512.png (generated from Liberty logo) |
| `templates/player_index.html` | EDIT — Ensure `<link rel="manifest">`, register SW inline |
| `templates/playbook.html` (share view) | VERIFY — Rendered play pages have `<link rel="manifest">` and SW registration (inject in `_build_player_site` if missing) |

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
| `blueprints/playbook.py` | KEEP — Publish route returns `{"ok": True, "count": N, "url": "http://localhost:8080/player.html"}` |

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
| `templates/playbook.html` (share view) | EDIT — Inject `player-code-gate.js` and modal into rendered play pages (in `_build_player_site`) |
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
| 1 | `dist/player/player.html` lists ONLY visible plays; each `plays/<id>/index.html` animates correctly from whitelisted choreography (served on localhost:8080) | ✅ Eye-check: play animates correctly; hidden plays absent from `dist/player/plays/`; zero-visible case works |
| 2 | PWA installs, works offline | ✅ Eye-check: home screen icon, airplane mode works |
| 3 | One-click Publish from playbook toolbar | ✅ Eye-click: button shows count, toast confirms, `http://localhost:8080/player.html` link opens correct plays |
| 4 | Public URL (free hosting, drag-and-drop) | ✅ Eye-check: deployed URL works on phone, installs, shows only visible plays |
| 5 | Optional team code (soft lock) | ✅ Eye-check: code gate works, no PII collected, honest about static-host limits |

---

## Notes for Coder (Claude Code)

- **Reuse the share view:** The player app is built by rendering `templates/playbook.html` with `view_mode="share"` for each visible play. Do not copy animation code into a separate `player-viewer.js`. The share view already uses the exact same animation engine as the main program.
- **Static choreography JSON:** Write whitelisted choreography to `plays/<id>/choreography` (NO .json extension). The share view's `loadStickyChoreographyDoc()` fetches `${shareAssetBase}/choreography`; in the static build, `shareAssetBase = "."` so it fetches `./choreography`. The file must be wrapped as `{"ok": true, "sticky": true, "choreography": <doc>}`. python http.server serves unknown extensions as application/octet-stream; fetch().json() still parses it.
- **No schema changes:** Use JSON files (`jrhigh_player_visibility.json`, `jrhigh_player_code.json`). If coder thinks a column is needed, stop and ask Scott.
- **Privacy:** Bundles omit `source_image`, `notes`. `court_frac` decision from Stage 0 measurement (keep if playback needs it; it's a number, not private). Whitelist fields in choreography per step. No `analytics.js`, no `fetch` to third parties, no cookies (localStorage only for code gate).
- **Static output:** Stage 4 build script (`scripts/build_player_site.py`) runs against Scott's LOCAL DB — no runtime DB on static host. `dist/player/` and visibility/code JSON files are gitignored.
- **Public repo:** Generated bundles NEVER committed. `dist/player/` and `data/playbook/jrhigh_player_*.json` in `.gitignore`.
- **Run command:** Entry point is `& C:\Users\scott\Documents\liberty-basketball-analysis\.venv\Scripts\python.exe app.py` (app.py line 288). Use this in all test commands.
- **Testing:** Each stage has explicit "How Scott checks by eye" — coder must verify these before calling stage done.
- **Standalone pages:** Rendered play pages are complete HTML documents. The top-level `player.html` is a standalone template (`player_index.html`) that does NOT extend `base.html`.
- **Stage 1 test uses localhost, not file://:** `python -m http.server 8080 -d dist/player` — browsers block fetch() and SW on file://.
- **Path fix:** `dist/` is at repo root (gitignored), not outside the repo. Use `Path(current_app.root_path) / "dist" / "player"`.
- **Rebuild from scratch:** `_build_player_site` deletes `dist/player/` entirely before writing, so hidden plays are gone and zero-visible case is clean.
- **Column names:** `play_steps` uses `step_number`, `positions_json`, `movements_json` (schema.sql). Choreography whitelist applied PER STEP inside `choreography.steps[]` — top-level choreography has no positions/movements/ball.
- **Database for testing:** The liberty-playbook worktree has NO film_analysis.db. Use `C:\Users\scott\Documents\liberty-basketball-analysis\.venv\Scripts\python.exe` and set `LIBERTY_DATABASE` to a COPY of the real DB placed OUTSIDE the repo (C:\Users\scott\Documents\Liberty_Playbook_TestDB; a copy inside the worktree is not gitignored and the repo is public) (never the live DB from a dev branch).
- **Live film_analysis.db opened read-only only; tests use tmp_path copies only.** Do not edit any other file, do not create scratch files in the repo.

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

## Measurement Results Template (`.team/specs/10_measurement_results.md`)

Fill this after Stage 0 measurement:

```markdown
# Measurement Results — Unknowns 1–3

Date: YYYY-MM-DD
Plays tested: <play_id_1> (<name>), <play_id_2> (<name>), <play_id_3> (<name>)

## Unknown 1: Choreography-only animation
| Play ID | Choreography-only? | Server endpoints hit during Play All |
|---------|-------------------|--------------------------------------|
| 1       | YES/NO            | (list or "none")                     |
| 2       | YES/NO            | (list or "none")                     |
| 3       | YES/NO            | (list or "none")                     |

Notes:

## Unknown 2: Sheet images requested during playback
| Play ID | Sheet images requested? | Which steps / URLs |
|---------|------------------------|--------------------|
| 1       | YES/NO                 |                    |
| 2       | YES/NO                 |                    |
| 3       | YES/NO                 |                    |

Notes:

## Unknown 3: Phone layout & offline
| Check | Result | Notes |
|-------|--------|-------|
| iPhone SE layout fits, no horizontal scroll | PASS/FAIL | |
| Pixel 7 layout fits, no horizontal scroll | PASS/FAIL | |
| Touch playback works (tap Play, step buttons) | PASS/FAIL | |
| Share view includes navbar/sidebar? | YES/NO | What chrome appears? |
| Offline (SW) — page loads | PASS/FAIL | |
| Offline — playback works | PASS/FAIL | |
| Assets needed for precache | (list) | |

Decision: Proceed to Stage 1 / Adjust plan (explain)
```