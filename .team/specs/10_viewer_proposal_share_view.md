# Proposal from the playbook coder (Claude Code), 2026-10-28 - for Hermes to plan

Scott approved sending this to Hermes. It changes plan 10 v5 (viewer section only); the server side (visibility switch, Publish, rebuild, whitelist) stays.

## Finding (measured)
- Plan v5 copies playback functions from templates/playbook.html into static/js/player-viewer.js.
- A call-graph closure from the viewer's entry points (script lines 664-7704 of templates/playbook.html, 254 top-level functions) needs 141 functions, not ~49. Many are editor/DOM-bound (updateStepList, showArrowEditor, deleteChoreographyPlayer, buildChoreographyPayload) or call the server (fetchSheetInkPaths, ensureSheetAlignment, sheetApiUrl -> POST sheet-extract/sheet-paths). Copy-by-hand failed three times.

## Proposal
Build the player app from the EXISTING read-only share view instead of a copied engine:
- blueprints/playbook.py already renders templates/playbook.html with view_mode="share" (route /play/share/<token>, lines ~1087-1121); isReadOnly is true there and the same animation code runs.
- At Publish, _build_player_site would render that same template in share/view mode for each VISIBLE play into dist/player/plays/<id>/index.html, and write the play's whitelisted choreography as a static file at the URL the page fetches (loadStickyChoreographyDoc fetches `${shareAssetBase}/choreography`, playbook.html script line ~2919), with shareAssetBase pointing at the static folder.
- Result: identical animation by construction (the playbook's own code), no sync check to maintain.

## Unknowns Hermes must plan around (measure first, do not assume)
1. Does every visible play animate from its saved choreography alone (no POST to sheet-extract/sheet-paths)? Plays without saved choreography would need the server: decide (exclude them from Publish, or bake their paths at Publish time).
2. Privacy: source sheets (FastDraw/FastScout images) must not ship (requirement 7 and plan v5 whitelist). Does the share view request sheet images during playback of a choreographed play? If yes, how is that avoided?
3. Does the share page work on a phone (layout, touch, size) and offline as a PWA (static asset paths from url_for -> relative paths; man_defense.js, playbook-taxonomy.js, playbook-dnd.js, playbook-export.js)?
4. The page extends the program's layout (navbar etc.); what must be hidden for players.
5. Scott's requirements file: .team/specs/10_jrhigh_requirements_scott.md (minors: no logins, names, analytics; one-way sync; Jan 4, 2027).

## Ask
Hermes: write plan 10 v6 (viewer section), starting with a measurement step for unknowns 1-3 on 2-3 real plays before any build. Keep the v5 server side. Plain Markdown, no line-number prefixes.
