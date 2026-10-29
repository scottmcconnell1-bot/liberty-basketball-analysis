REJECTED by Claude Code, 2026-10-27: Good staged shape and eye-checks, but: (1) Misses Scott requirement 6 (.team/specs/10_jrhigh_requirements_scott.md): export ALL plays to Scott side, a "Visible to players" on/off switch per play, Publish ships ONLY visible plays, turning one off and republishing removes it. The plan has per-play export, an append-only manifest (never removes), and limits export to team_key jh_boys/jh_girls. (2) Hidden plays leak: Stage 1 writes bundles under static/jrhigh_player/ and adds public /player routes to the main app, which serves all of static/; an exported-then-hidden play stays downloadable. Bundles for the phone app must contain only visible plays and live outside the main app static/ tree. (3) The GitHub repo is PUBLIC (gh repo view: visibility PUBLIC): Stage 4 gh-pages / committed bundles would publish plays to the world. Say so; keep generated bundles out of the repo; offer hosting where only the built site is uploaded. (4) Stage 4 Cloudflare/GitHub build "reads DB": film_analysis.db is gitignored, so a cloud build cannot read it. Build locally on Scott PC, upload only the built folder. (5) Stage 5 team code via Flask cookie cannot work on a static host; on static hosting a code is only a soft lock (anyone with the files can read them). State that honestly and pick a design consistent with the chosen hosting. (6) Minors/privacy: bundle carries source_image (scout PDF page, may show opponent and notes) and notes; strip both unless Scott allows. The viewer must be a standalone page, not extend base.html (it carries the main app nav and Sign In). (7) Run command "python -m app # or whatever": the entry is .\.venv\Scripts\python.exe app.py (app.py line 288). (8) Copying ~1900 lines of animation from playbook.html means fixes in the main program never reach the app; state the trade-off and how the copy is kept in step (e.g. one shared JS file, only if playbook.html behaviour is proven unchanged; otherwise a copy plus a check that both render the same play identically).

# Jr High Player App — Staged Plan

**Goal:** A separate PLAYER app for Jr High team. Shows ONLY animated plays Scott picks. Players/parents use on phones. Scott draws/edits in main program; playbook unchanged. Sync ONE-WAY: main → player. Delivery: installable web app (PWA: Add to Home Screen, own icon, full screen, works offline after first load, iPhone/Android, no app store). Publishing: Scott marks plays as Jr High and clicks Publish; app updates next open. Privacy: minors — no logins, no names, no analytics, no data collected; plays only; optional team code to open.

**Key existing pieces to reuse:**
- `blueprints/playbook.py`: share routes `/play/share/<token>` and `/play/share/<token>/choreography` are public, no auth
- `playbook_choreography.py`: sticky choreography JSON at `data/playbook/choreography/{play_id}.json`
- Animation: inline SVG/JS in `templates/playbook.html` (lines 624–2500+) and `static/js/playbook-export.js` (video recording)
- Plays table has `team_key` (jh_boys, jh_girls, hs_boys, hs_girls) — already in DB via additive ALTER
- Export: `/playbook/export/<id>` returns play + steps JSON

**Schema decision:** NO schema.sql change. Jr High list kept in a JSON file (`data/playbook/jrhigh_player_plays.json`). If Scott later wants multi-team or metadata, that becomes a gate.

---

## Stage 1 — Smallest Working Slice (Export + Phone Viewer)

**What it does:** Scott clicks "Export for Player App" on a play. A static JSON bundle is written to `static/jrhigh_player/`. A tiny viewer page (`/player`) reads the bundle and animates using existing animation code. Testable on Scott's PC at `http://localhost:5000/player`.

### Files for Stage 1

| File | Action | Purpose |
|------|--------|---------|
| `blueprints/playbook.py` | ADD route `@playbook_bp.route("/playbook/play/<int:play_id>/export-player", methods=["POST"])` | Export one play to player bundle |
| `blueprints/playbook.py` | ADD route `@playbook_bp.route("/player")` (public, no auth, no feature flag) | Player viewer page |
| `blueprints/playbook.py` | ADD helper `_build_player_bundle(play_id, db)` | Build JSON bundle: play meta + steps + choreography |
| `templates/player.html` | CREATE new template | Minimal viewer: court SVG + play selector + Play All button |
| `static/js/player-viewer.js` | CREATE new file | Animation logic copied/adapted from `playbook.html` inline script |
| `data/playbook/jrhigh_player_plays.json` | CREATE (empty list `[]`) | Manifest of play_ids Scott publishes |
| `static/jrhigh_player/` | CREATE directory | Output folder for static bundles (gitignored) |

### New Route: Export for Player App
```python
@playbook_bp.route("/playbook/play/<int:play_id>/export-player", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def playbook_export_player(play_id):
    db = get_db()
    play = db.execute("SELECT * FROM plays WHERE id = ?", (play_id,)).fetchone()
    if not play:
        return jsonify({"error": "Play not found"}), 404
    # Only Jr High team plays can be exported
    if play["team_key"] not in ("jh_boys", "jh_girls"):
        return jsonify({"error": "Only Jr High plays can be exported to Player App"}), 400
    bundle = _build_player_bundle(play_id, db)
    # Write to static/jrhigh_player/{play_id}.json
    out_dir = Path(current_app.root_path) / "static" / "jrhigh_player"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{play_id}.json"
    out_path.write_text(json.dumps(bundle, indent=2))
    # Update manifest
    manifest_path = Path(current_app.root_path) / "data" / "playbook" / "jrhigh_player_plays.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
    if play_id not in manifest:
        manifest.append(play_id)
        manifest_path.write_text(json.dumps(manifest, indent=2))
    return jsonify({"ok": True, "play_id": play_id, "url": url_for("playbook.player_view", play_id=play_id)})
```

### New Route: Player Viewer
```python
@playbook_bp.route("/player")
def player_index():
    # Public, no auth, no feature flag
    manifest_path = Path(current_app.root_path) / "data" / "playbook" / "jrhigh_player_plays.json"
    play_ids = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
    db = get_db()
    plays = []
    for pid in play_ids:
        p = db.execute("SELECT id, name, category, team_key FROM plays WHERE id = ?", (pid,)).fetchone()
        if p:
            plays.append(dict(p))
    return render_template("player.html", plays=plays)

@playbook_bp.route("/player/play/<int:play_id>")
def player_view(play_id):
    # Public, no auth
    bundle_path = Path(current_app.root_path) / "static" / "jrhigh_player" / f"{play_id}.json"
    if not bundle_path.exists():
        return "Play not found", 404
    bundle = json.loads(bundle_path.read_text())
    return render_template("player.html", play=bundle, plays=[])
```

### Player Bundle Structure (`_build_player_bundle`)
```json
{
  "play": { "id": 101, "name": "Horns Entry", "category": "offense", "team_key": "jh_boys" },
  "steps": [
    {
      "step_index": 0,
      "label": "Picture 1",
      "notes": "",
      "positions": { "o1": {"x":250,"y":360}, "o2":{...}, ... },
      "ball": "o1",
      "movements": [ { "type":"cut","from":"o1","to":"o1","anchors":[...],"timing":"after","shape":"straight" }, ... ],
      "source_image": "/uploads/.../page_0050.png"
    },
    ...
  ],
  "choreography": { ...loaded from data/playbook/choreography/101.json... }
}
```

### `templates/player.html` (minimal)
- Extends `base.html` but overrides content block only
- No sidebar, no editor toolbar, no save buttons
- Top bar: play selector dropdown (shows play names from manifest)
- Court SVG (same viewBox 0 0 500 470, same court drawing)
- Playback controls: ▶ Play All, ⏸ Stop, ◀ Back, ▶ Next step
- Loads `static/js/player-viewer.js`
- If `play` passed: auto-load that play; else show selector

### `static/js/player-viewer.js` (adapted from playbook.html)
- Copy animation engine: `renderCourt()`, `syncPlayerTokens()`, `animateGroup()`, `playPhases()`, `positionsThrough()`, `pointAlong()`, `groupsOf()`
- Strip: editor tools, drag handlers, undo/redo, choreography save, sheet underlay, step list panel, category tree
- Keep: `ANIM` timing constants, `renderStep()`, `playAnimation()` (renamed `playAll()`), `stepForwardPlay()`, `rewindPlay()`
- Data source: `window.PLAYER_BUNDLE` injected via template script tag
- `steps` array built from bundle.steps + bundle.choreography (sticky positions/movements win)

### Run / Test Commands (Stage 1)
```bash
# 1. Start dev server
cd /mnt/c/Users/scott/Documents/liberty-playbook
python -m app  # or whatever the entry point is

# 2. In browser: open http://localhost:5000/playbook, pick a Jr High play, click "Export for Player App"
#    (button added to playbook.html play row actions for jh_boys/jh_girls plays)

# 3. Open http://localhost:5000/player
#    - Dropdown lists exported plays
#    - Select one → court renders with players in step 1 positions
#    - Click ▶ Play All → players animate through all steps
#    - Click ◀ Back / ▶ Next step → step through manually
#    - Works on mobile Chrome/ Safari (test via Chrome DevTools device toolbar)
```

### How Scott Checks by Eye (Stage 1)
1. Go to `/playbook`, filter to Jr High Boys team
2. Pick a play (e.g., "Horns Entry"), click **Export for Player App** (new button on row)
3. Go to `/player` — play appears in dropdown
4. Select it — court shows 5 offense tokens in correct start spots
5. Click **▶ Play All** — tokens move smoothly along arcs/lines, ball passes animate, holds at each step
6. Click **◀ Back** — rewinds one action; **▶ Next step** — advances one action
7. Open Chrome DevTools → Device Toolbar → iPhone SE / Pixel 7 — layout fits, touch works, no horizontal scroll
8. Refresh `/player` — play still there (static JSON persisted)

---

## Stage 2 — PWA: Installable + Offline

**What it adds:** Service worker, manifest, icons, cache-first strategy. After first load, `/player` works offline (no network). "Add to Home Screen" shows custom icon, launches full-screen.

### Files for Stage 2
| File | Action |
|------|--------|
| `static/manifest.json` | CREATE — PWA manifest (name, icons, start_url, display: standalone) |
| `static/sw.js` | CREATE — Service worker (cache static assets + player bundles) |
| `templates/player.html` | EDIT — Add `<link rel="manifest">`, register SW inline |
| `static/icons/` | CREATE — icon-192.png, icon-512.png (generated from Liberty logo) |

### Service Worker Strategy
- **Precache:** `/player`, `/static/js/player-viewer.js`, `/static/css/playbook.css` (court styles), manifest, icons
- **Runtime cache (stale-while-revalidate):** `/player/play/<id>` (but bundles are static files under `/static/jrhigh_player/` so cache-first)
- **Offline fallback:** cached `/player` shell shows last-loaded play bundle (bundles are static files, cached on first visit)

### Run / Test Commands (Stage 2)
```bash
# 1. Restart server
python -m app

# 2. Open http://localhost:5000/player on phone (or Chrome DevTools mobile)
#    - Chrome: "Install app" prompt appears / menu → "Add to Home Screen"
#    - iOS Safari: Share → "Add to Home Screen"
# 3. Launch from home screen — full screen, no browser chrome, Liberty icon
# 4. Turn on Airplane mode → reload — play still animates
# 5. Reconnect → SW updates cache silently on next visit
```

### How Scott Checks by Eye (Stage 2)
- Install on iPhone and Android → icon appears, opens full-screen
- Airplane mode → app loads, play animates
- Back online → no error, no double-load

---

## Stage 3 — Publish Button (One-Click from Main Program)

**What it adds:** In main playbook UI, a "Publish to Player App" button on Jr High plays. One click = export + manifest update. No separate export step.

### Files for Stage 3
| File | Action |
|------|--------|
| `templates/playbook.html` | EDIT — Add "Publish to Player App" button on play row (only for jh_boys/jh_girls, only in list view) |
| `static/js/playbook-dnd.js` or inline | ADD — POST to `/playbook/play/<id>/export-player`, show toast "Published to Player App" |
| `blueprints/playbook.py` | EDIT — Export route returns `{"ok": True, "player_url": "/player/play/<id>"}` for toast link |

### Run / Test Commands (Stage 3)
```bash
# 1. Restart server
# 2. /playbook → Jr High Boys → pick play → click "Publish to Player App"
# 3. Toast appears: "Published to Player App" with link
# 4. Open /player on phone (or new tab) — play is there instantly
# 5. Edit play in main program → click Publish again → /player shows updated animation on refresh
```

### How Scott Checks by Eye (Stage 3)
- One click publishes
- Phone viewer updates on refresh (no rebuild, no deploy)
- Edit → Publish → phone shows new version

---

## Stage 4 — Hosting Options (Free First)

**Goal:** Scott hosts the player app publicly so players/parents access via URL. No app store. Free tier first.

| Option | Cost | Setup | Pros | Cons |
|--------|------|-------|------|------|
| **GitHub Pages** | Free | Push `static/jrhigh_player/` + `player.html` + assets to `gh-pages` branch | Free HTTPS, custom domain, CDN | Static only — no Python. Need to pre-generate bundles. |
| **Cloudflare Pages** | Free | Connect repo, build command: `python build_player.py` | Free, fast, custom domain, Functions for dynamic if needed | Build minutes limit |
| **Render.com Free Web Service** | Free | `git push` → auto-deploy | Runs Python/Flask, HTTPS, custom domain | Spins down after 15 min inactivity (cold start ~30s) |
| **Fly.io** | Free allowance | `fly launch` → deploy | Runs containers, global, HTTPS | Requires Dockerfile, CLI |
| **Railway** | $5/mo after trial | GitHub connect | Simple, runs Python | Not free long-term |

**Recommended for Scott (free first):** **Cloudflare Pages** with a small build script.
- Build script: `python scripts/build_player_site.py` → reads DB, writes `dist/player.html`, `dist/static/jrhigh_player/*.json`, copies `static/js/player-viewer.js`, `static/css/playbook.css`, icons, manifest, sw.js
- Deploy: connect repo → Cloudflare builds on push to `main`
- Domain: `player.libertybball.com` (or `jh-players.libertybball.com`)

**Alternative (simplest):** GitHub Pages + GitHub Action that runs export script nightly. Scott clicks "Publish" → commits bundles → Action builds site.

### Files for Stage 4
| File | Action |
|------|--------|
| `scripts/build_player_site.py` | CREATE — Reads DB, generates static site to `dist/` |
| `.github/workflows/player-site.yml` | CREATE — GitHub Action: on push to `main` (or manual dispatch), runs build, deploys to `gh-pages` |
| `static/jrhigh_player/` | ADD to `.gitignore` (generated, not committed) |

### Run / Test Commands (Stage 4)
```bash
# Local test of static build
cd /mnt/c/Users/scott/Documents/liberty-playbook
python scripts/build_player_site.py
# Serves dist/ with: python -m http.server -d dist 8080
# Open http://localhost:8080/player.html — works offline, no Python backend

# Deploy: push to main → GitHub Action runs → site at https://scottmcconnell.github.io/liberty-playbook/player.html
```

### How Scott Checks by Eye (Stage 4)
- Open deployed URL on phone → installs as PWA
- Airplane mode → works
- Click "Publish" in main app → push → wait 2 min → phone shows new play

---

## Stage 5 — Team Code (Optional Privacy Gate)

**What it adds:** Optional 4–6 character code (e.g., "LIBERTY25") to open the player app. No user accounts, no names. Code stored in `data/playbook/jrhigh_player_code.json` (or app_settings table). If set, `/player` and `/player/play/<id>` require `?code=XXX` or cookie.

### Files for Stage 5
| File | Action |
|------|--------|
| `blueprints/playbook.py` | EDIT — `player_index` and `player_view` check code if configured |
| `templates/player.html` | EDIT — If code required and not in cookie, show code entry screen first |
| `data/playbook/jrhigh_player_code.json` | CREATE — `{"code": "LIBERTY25"}` (Scott sets once) |

### Run / Test Commands (Stage 5)
```bash
# 1. Create code file
echo '{"code": "LIBERTY25"}' > data/playbook/jrhigh_player_code.json

# 2. Restart server
# 3. Open /player → shows "Enter team code" screen
# 4. Enter wrong code → "Invalid code"
# 5. Enter LIBERTY25 → saves cookie, shows play list
# 6. Close/reopen browser → cookie remembered, goes straight to plays
# 7. Share URL with code: /player?code=LIBERTY25 → works without cookie
```

### How Scott Checks by Eye (Stage 5)
- Without code: blocked at entry screen
- With code: full access, persists across sessions
- No names, no emails, no analytics — just the code

---

## Summary: Stage Gates

| Stage | Deliverable | Scott Gate |
|-------|-------------|------------|
| 1 | `/player` animates exported Jr High plays on PC/phone | ✅ Eye-check: play animates correctly |
| 2 | PWA installs, works offline | ✅ Eye-check: home screen icon, airplane mode works |
| 3 | One-click Publish from playbook | ✅ Eye-click: button appears, toast confirms, phone updates |
| 4 | Public URL (free hosting) | ✅ Eye-check: deployed URL works on phone, installs |
| 5 | Optional team code | ✅ Eye-check: code gate works, no PII collected |

---

## Notes for Coder (OpenCode)

- **Reuse animation code:** Copy from `templates/playbook.html` (lines ~624–2500) into `static/js/player-viewer.js`. Do not rewrite animation logic.
- **No schema changes:** Use JSON manifest file. If coder thinks a column is needed, stop and ask Scott.
- **Privacy:** No `analytics.js`, no `fetch` to third parties, no cookies except optional team code.
- **Static output:** Stage 4 build script must run against Scott's local DB (or exported JSON) — no runtime DB on static host.
- **Testing:** Each stage has explicit "How Scott checks by eye" — coder must verify these before calling stage done.