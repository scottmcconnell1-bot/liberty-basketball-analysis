REJECTED by Claude Code, 2026-10-27 (v3): v3 fixes all seven v2 points (rebuild from scratch incl. zero-visible, repo-root dist/, localhost serving, one template, byte-compare of named unchanged functions, Windows paths). Checked against schema.sql and data/playbook/choreography/101.json: (1) play_steps columns are step_number, label, positions_json, movements_json, notes, source_image (schema.sql); there is no step_index, positions, movements or ball column, so step["step_index"] / step["ball"] raise. Use the real columns. (2) Choreography whitelist is applied to TOP-LEVEL keys, but the file is {version, play_id, updated_at, source, sticky, steps:[{step_index, source_image, court_frac, positions, coachOrder, movements, ink:{paths, marks, passes, actions}}]}. Top-level positions/movements/ball do not exist, so every bundle gets an EMPTY choreography and Scott hand-made plays publish blank. Whitelist PER STEP: step_index, positions, coachOrder, movements, ink (paths, marks, passes, actions); drop source_image, court_frac. (3) The liberty-playbook worktree has NO .venv and NO film_analysis.db (gitignored). Use C:\Users\scott\Documents\liberty-basketball-analysis\.venv\Scripts\python.exe, and for testing set LIBERTY_DATABASE to a COPY of the real DB placed in the worktree (never the live DB from a dev branch). (4) Stage 2 says open http://localhost:8080 on the phone; a phone cannot reach the PC localhost. Phone install is tested only after Stage 4 hosting (as the plan says in Stage 1).

# Jr High Player App — Staged Plan

**Goal:** A separate PLAYER app for Jr High team. Shows ONLY animated plays Scott picks. Players/parents use on phones. Scott draws/edits in main program; playbook unchanged. Sync ONE-WAY: main → player. Delivery: installable web app (PWA: Add to Home Screen, own icon, full screen, works offline after first load, iPhone/Android, no app store). Publishing: Scott marks plays as "Visible to players" and clicks Publish; app updates next open. Hidden plays are NOT shipped at all (not merely hidden in UI). Privacy: minors — no logins, no names, no analytics, no data collected; plays only; optional team code (soft lock on static host). Target ready: Jan 4, 2027.

**Key existing pieces to reuse:**
- `blueprints/playbook.py`: share routes `/play/share/<token>` and `/play/share/<token>/choreography` are public, no auth
- `playbook_choreography.py`: sticky choreography JSON at `data/playbook/choreography/{play_id}.json`
- Animation: inline SVG/JS in `templates/playbook.html` (lines 624–2500+) and `static/js/playbook-export.js` (video recording)
- Plays table has `team_key` (jh_boys, jh_girls, hs_boys, hs_girls) — already in DB via additive ALTER
- Export: `/playbook/export/<id>` returns play + steps JSON

**Schema decision:** NO schema.sql change. Visibility list kept in a JSON file (`data/playbook/jrhigh_player_visibility.json`). If Scott later wants multi-team or metadata, that becomes a gate.

**Animation code trade-off:** The animation engine (~1900 lines in `playbook.html` inline script) is copied into `static/js/player-viewer.js` for Stage 1 so the player app is a standalone static site with no Flask dependency. This means fixes in the main program do NOT automatically reach the player app. Mitigation: a shared-source check script (`scripts/check_animation_sync.py`) compares the copied functions against the source in `playbook.html` and flags drift. If Scott confirms `playbook.html` animation behavior is stable, we can later extract a single shared JS module loaded by both; until then, copy + check is the contract.

---

## Stage 1 — Smallest Working Slice (Export ALL + Visibility Toggle + Phone Viewer)

**What it does:** Scott sees ALL plays in the main program with a "Visible to players" toggle per play. Clicking "Publish to Player App" builds a static site in `dist/player/` containing ONLY visible plays. A tiny viewer page (`dist/player/player.html`) reads the bundle and animates using copied animation code. Testable on Scott's PC by serving `dist/player/` via `python -m http.server` on localhost:8080 (browsers block fetch() from file://; service workers need https or localhost). Phone install/offline (Stage 2) can only be tested on the PC (localhost) until Stage 4 hosting gives https.

### Files for Stage 1

| File | Action | Purpose |
|------|--------|---------|
| `blueprints/playbook.py` | ADD route `@playbook_bp.route("/playbook/play/<int:play_id>/visibility", methods=["POST"])` | Toggle "Visible to players" for any play (ALL team_keys) |
| `blueprints/playbook.py` | ADD route `@playbook_bp.route("/playbook/publish-player", methods=["POST"])` | Build static player site to `dist/player/` with ONLY visible plays |
| `blueprints/playbook.py` | ADD helper `_build_player_site(db)` | Generate `dist/player/player.html`, `dist/player/plays/*.json`, copy assets |
| `templates/playbook.html` | EDIT — Add "Visible to players" toggle switch on every play row; add "Publish to Player App" button | Scott controls visibility per play; one-click publish |
| `data/playbook/jrhigh_player_visibility.json` | CREATE (empty object `{}`) | Persisted map: `play_id` → `true/false` (visible to players) |
| `templates/player.html` | CREATE new STANDALONE template (does NOT extend base.html) | Minimal viewer: court SVG + play selector + Play All button |
| `static/js/player-viewer.js` | CREATE new file | Animation logic copied/adapted from `playbook.html` inline script |
| `static/css/player.css` | CREATE new file | Court styles extracted from `playbook.css` (no main app nav/styles) |
| `scripts/check_animation_sync.py` | CREATE | Compares `player-viewer.js` functions against `playbook.html` source; flags drift |
| `dist/player/` | CREATE directory (gitignored) | Output folder for static player site (NOT under `static/`) |

### New Route: Toggle Visibility (ALL plays, any team_key)

```python
@playbook_bp.route("/playbook/play/<int:play_id>/visibility", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def playbook_toggle_visibility(play_id):
    db = get_db()
    play = db.execute("SELECT id FROM plays WHERE id = ?", (play_id,)).fetchone()
    if not play:
        return jsonify({"error": "Play not found"}), 404
    data = request.get_json() or {}
    visible = bool(data.get("visible", False))
    manifest_path = Path(current_app.root_path) / "data" / "playbook" / "jrhigh_player_visibility.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest[str(play_id)] = visible
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return jsonify({"ok": True, "play_id": play_id, "visible": visible})
```

### New Route: Publish to Player App (builds static site with ONLY visible plays)

```python
@playbook_bp.route("/playbook/publish-player", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def playbook_publish_player():
    db = get_db()
    result = _build_player_site(db)
    return jsonify(result)

def _build_player_site(db):
    # Load visibility map
    manifest_path = Path(current_app.root_path) / "data" / "playbook" / "jrhigh_player_visibility.json"
    visibility = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    visible_ids = [int(pid) for pid, vis in visibility.items() if vis]

    # Build output directory OUTSIDE static/ tree (root_path is repo root; dist/ is gitignored)
    out_dir = Path(current_app.root_path) / "dist" / "player"
    plays_dir = out_dir / "plays"

    # REBUILD FROM SCRATCH: delete everything, then write only visible plays
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    plays_dir.mkdir(parents=True, exist_ok=True)

    # Copy static assets (JS, CSS, icons, manifest, SW)
    for asset in ["player-viewer.js"]:
        src = Path(current_app.root_path) / "static" / "js" / asset
        dst = out_dir / asset
        if src.exists():
            shutil.copy2(src, dst)
    for asset in ["player.css"]:
        src = Path(current_app.root_path) / "static" / "css" / asset
        dst = out_dir / asset
        if src.exists():
            shutil.copy2(src, dst)
    for asset in ["manifest.json", "sw.js"]:
        src = Path(current_app.root_path) / "static" / asset
        dst = out_dir / asset
        if src.exists():
            shutil.copy2(src, dst)
    icons_src = Path(current_app.root_path) / "static" / "icons"
    if icons_src.exists():
        shutil.copytree(icons_src, out_dir / "icons", dirs_exist_ok=True)

    # Write per-play bundles (PRIVACY: whitelist fields; omit source_image, notes, court_frac)
    play_list = []
    for pid in visible_ids:
        play = db.execute("SELECT * FROM plays WHERE id = ?", (pid,)).fetchone()
        if not play:
            continue
        steps = db.execute("SELECT * FROM play_steps WHERE play_id = ? ORDER BY step_index", (pid,)).fetchall()
        choreo_path = Path(current_app.root_path) / "data" / "playbook" / "choreography" / f"{pid}.json"
        choreo = json.loads(choreo_path.read_text()) if choreo_path.exists() else {}

        # Whitelist play fields
        bundle = {
            "play": {
                "id": play["id"],
                "name": play["name"],
                "category": play["category"],
                "team_key": play["team_key"]
            },
            "steps": [],
            "choreography": {}
        }

        # Whitelist step fields
        for step in steps:
            step_data = {
                "step_index": step["step_index"],
                "label": step["label"],
                "positions": json.loads(step["positions"]) if step["positions"] else {},
                "ball": step["ball"],
                "movements": json.loads(step["movements"]) if step["movements"] else []
            }
            bundle["steps"].append(step_data)

        # Whitelist choreography fields (strip source_image, court_frac, notes)
        if choreo:
            bundle["choreography"] = {}
            for key, value in choreo.items():
                if key in ("positions", "movements", "ball"):  # whitelist only
                    bundle["choreography"][key] = value

        (plays_dir / f"{pid}.json").write_text(json.dumps(bundle, indent=2))
        play_list.append({
            "id": play["id"],
            "name": play["name"],
            "category": play["category"],
            "team_key": play["team_key"]
        })

    # Write index manifest (list of visible plays for the selector)
    (out_dir / "plays_index.json").write_text(json.dumps(play_list, indent=2))

    # Render standalone player.html (no base.html, no Flask template engine at runtime)
    player_html = render_template("player.html", plays=play_list)
    (out_dir / "player.html").write_text(player_html)

    return {"ok": True, "count": len(play_list), "url": f"http://localhost:8080/player.html"}
```

### `templates/player.html` (STANDALONE — does NOT extend base.html)

- Complete HTML document: `<!DOCTYPE html>`, `<html>`, `<head>`, `<body>`
- No sidebar, no editor toolbar, no save buttons, no main app nav, no Sign In link
- Top bar: play selector dropdown (shows play names from `plays_index.json`)
- Court SVG (same viewBox 0 0 500 470, same court drawing as main app)
- Playback controls: ▶ Play All, ⏸ Stop, ◀ Back, ▶ Next step
- Loads `player-viewer.js`, `player.css`, registers SW
- If URL has `?play=<id>`: auto-load that play; else show selector
- Inline script: `window.PLAYS_INDEX = {{ plays | tojson }};`

### `static/js/player-viewer.js` (copied from `playbook.html` lines ~624–2500)

- Copy animation engine: `renderCourt()`, `syncPlayerTokens()`, `animateGroup()`, `playPhases()`, `positionsThrough()`, `pointAlong()`, `groupsOf()`
- Strip: editor tools, drag handlers, undo/redo, choreography save, sheet underlay, step list panel, category tree, any Flask/template-specific code
- Keep: `ANIM` timing constants, `renderStep()`, `playAnimation()` (renamed `playAll()`), `stepForwardPlay()`, `rewindPlay()`
- Data source: loads `plays_index.json` on init; on play select, fetches `plays/<id>.json`
- `steps` array built from bundle.steps + bundle.choreography (sticky positions/movements win)

### `scripts/check_animation_sync.py` (byte-for-byte comparison of UNCHANGED functions)

- Define the EXACT list of functions that are copied WITHOUT adaptation:
  - `renderCourt()`
  - `syncPlayerTokens()`
  - `animateGroup()`
  - `playPhases()`
  - `positionsThrough()`
  - `pointAlong()`
  - `groupsOf()`
  - `ANIM` (the timing constants object)
- Extract each function's source text from `playbook.html` (between its `function name(` and the matching `}` at the same indent) and from `player-viewer.js`
- Compare byte-for-byte; any difference = drift flag
- Do NOT compare adapted/stripped functions (`playAll`, `stepForwardPlay`, `rewindPlay`, `renderStep`) — those are expected to differ
- Run as part of publish; fail build if drift detected on the unchanged set

### Run / Test Commands (Stage 1)

```bash
# 1. Start dev server (entry point is app.py line 288)
cd C:\Users\scott\Documents\liberty-playbook
.\.venv\Scripts\python.exe app.py

# 2. In browser: open http://localhost:5000/playbook
#    - EVERY play row (all team_keys) shows "Visible to players" toggle
#    - Toggle a few Jr High plays ON, toggle one OFF
#    - Click "Publish to Player App" (new button in toolbar)

# 3. Serve the generated static site on localhost (NOT file://):
.\.venv\Scripts\python.exe -m http.server 8080 -d dist\player
#    Open http://localhost:8080/player.html
#    - Dropdown lists ONLY the visible plays
#    - Select one → court renders with players in correct start spots
#    - Click ▶ Play All → tokens move smoothly along arcs/lines, ball passes animate, holds at each step
#    - Click ◀ Back / ▶ Next step → step through manually
#    - Works on mobile Chrome/Safari (test via Chrome DevTools device toolbar)

# 4. Turn a play OFF in main program → click Publish again → refresh http://localhost:8080/player.html → play is GONE (not downloadable)
```

### How Scott Checks by Eye (Stage 1)

1. Go to `/playbook` — ALL plays (any team) show "Visible to players" toggle
2. Toggle ON a Jr High play (e.g., "Horns Entry"), toggle OFF another
3. Click **Publish to Player App** — toast confirms "Player app built: 1 play"
4. Open `http://localhost:8080/player.html` — only the ON play appears in dropdown
5. Select it — court shows 5 offense tokens in correct start spots
6. Click **▶ Play All** — tokens move smoothly along arcs/lines, ball passes animate, holds at each step
7. Click **◀ Back** — rewinds one action; **▶ Next step** — advances one action
8. Open Chrome DevTools → Device Toolbar → iPhone SE / Pixel 7 — layout fits, touch works, no horizontal scroll
9. In main program: turn the play OFF → click Publish → refresh `player.html` — play is GONE (not in dropdown, `plays/<id>.json` deleted)
10. Verify `dist/player/plays/` contains ONLY visible plays; hidden play's JSON file is removed
11. Zero-visible case: turn ALL plays OFF → click Publish → `dist/player/` rebuilt with empty `plays_index.json`, empty `plays/`, viewer shows empty selector (no error)

---

## Stage 2 — PWA: Installable + Offline

**What it adds:** Service worker, manifest, icons, cache-first strategy. After first load, `player.html` works offline (no network). "Add to Home Screen" shows custom icon, launches full-screen.

### Files for Stage 2

| File | Action |
|------|--------|
| `static/manifest.json` | CREATE — PWA manifest (name: "Liberty Jr High Plays", icons, start_url: "player.html", display: standalone) |
| `static/sw.js` | CREATE — Service worker (cache static assets + player bundles) |
| `static/icons/` | CREATE — icon-192.png, icon-512.png (generated from Liberty logo) |
| `templates/player.html` (build template) | EDIT — Ensure `<link rel="manifest">`, register SW inline |
| `scripts/check_animation_sync.py` | RUN as part of publish — fails build if animation drift detected |

### Service Worker Strategy

- **Precache:** `player.html`, `player-viewer.js`, `player.css`, `manifest.json`, `sw.js`, `icons/*`, `plays_index.json`
- **Runtime cache (cache-first):** `plays/*.json` (bundles are static files, cached on first visit)
- **Offline fallback:** cached `player.html` shell shows last-loaded play bundle

### Run / Test Commands (Stage 2)

```bash
# 1. Restart server
.\.venv\Scripts\python.exe app.py

# 2. Publish from main app (adds SW, manifest, icons to dist/player/)
# 3. Serve locally
.\.venv\Scripts\python.exe -m http.server 8080 -d dist\player
#    Open http://localhost:8080/player.html on phone (or Chrome DevTools mobile)
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
| `blueprints/playbook.py` | EDIT — Publish route returns `{"ok": True, "count": N, "url": "http://localhost:8080/player.html"}` |

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
- Local http://localhost:8080/player.html viewer updates on refresh (no rebuild, no deploy)
- Edit → Publish → viewer shows new version
- Hidden plays stay hidden (not in dist/player/plays/)

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
.\.venv\Scripts\python.exe scripts/build_player_site.py
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

**What it adds:** Optional 4–6 character code (e.g., "LIBERTY25") to open the player app. **On static hosting, this is a SOFT LOCK only** — anyone with the files can read them (no server to enforce). Code stored in `data/playbook/jrhigh_player_code.json` (Scott sets once). If set, `player.html` shows code entry screen; correct code sets a `localStorage` flag and redirects to play list. Wrong code = stay on entry screen. No cookies (static host), no server enforcement.

### Files for Stage 5

| File | Action |
|------|--------|
| `static/js/player-code-gate.js` | CREATE — Checks `localStorage` for `player_code_verified`; if not set and code configured, shows entry modal; verifies against `player_code.json` fetched at runtime |
| `dist/player/player_code.json` | GENERATED at publish — `{"code": "LIBERTY25"}` (only if Scott set a code) |
| `templates/player.html` (build template) | EDIT — Include `player-code-gate.js`, add code entry modal HTML |
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
| 1 | `dist/player/player.html` animates ONLY visible plays (served on localhost:8080) | ✅ Eye-check: play animates correctly; hidden plays absent from `dist/player/plays/`; zero-visible case works |
| 2 | PWA installs, works offline | ✅ Eye-check: home screen icon, airplane mode works |
| 3 | One-click Publish from playbook toolbar | ✅ Eye-click: button shows count, toast confirms, http://localhost:8080/player.html link opens correct plays |
| 4 | Public URL (free hosting, drag-and-drop) | ✅ Eye-check: deployed URL works on phone, installs, shows only visible plays |
| 5 | Optional team code (soft lock) | ✅ Eye-check: code gate works, no PII collected, honest about static-host limits |

---

## Notes for Coder (OpenCode)

- **Reuse animation code:** Copy from `templates/playbook.html` (lines ~624–2500) into `static/js/player-viewer.js`. Do not rewrite animation logic. Run `scripts/check_animation_sync.py` after any `playbook.html` animation change.
- **No schema changes:** Use JSON files (`jrhigh_player_visibility.json`, `jrhigh_player_code.json`). If coder thinks a column is needed, stop and ask Scott.
- **Privacy:** Bundles omit `source_image`, `notes`, `court_frac` (scout PDF may show opponent/notes). Whitelist fields in choreography. No `analytics.js`, no `fetch` to third parties, no cookies (localStorage only for code gate).
- **Static output:** Stage 4 build script (`scripts/build_player_site.py`) runs against Scott's LOCAL DB — no runtime DB on static host. `dist/player/` and visibility/code JSON files are gitignored.
- **Public repo:** Generated bundles NEVER committed. `dist/player/` and `data/playbook/jrhigh_player_*.json` in `.gitignore`.
- **Run command:** Entry point is `.\.venv\Scripts\python.exe app.py` (app.py line 288). Use this in all test commands.
- **Testing:** Each stage has explicit "How Scott checks by eye" — coder must verify these before calling stage done.
- **Standalone viewer:** `player.html` is a complete HTML document, does NOT extend `base.html`, has no Flask template dependencies at runtime.
- **Stage 1 test uses localhost, not file://:** `python -m http.server 8080 -d dist/player` — browsers block fetch() and SW on file://.
- **Path fix:** `dist/` is at repo root (gitignored), not outside the repo. Use `Path(current_app.root_path) / "dist" / "player"`.
- **Rebuild from scratch:** `_build_player_site` deletes `dist/player/` entirely before writing, so hidden plays are gone and zero-visible case is clean.