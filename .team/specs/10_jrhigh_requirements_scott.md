# Jr High player app: Scott's requirements (2026-10-27)

1. Player-facing app: animated plays only; view only, no editing; phones (players or parents).
2. Installable web app (PWA, Add to Home Screen, offline after first load). No app store.
3. Scott works on plays on his computer in the main program; the playbook stays in the main program unchanged.
4. One-way sync: main program -> player app.
5. Ready by Jan 4, 2027 (Jr High season start).
6. Play selection (Scott, 2026-10-27): "export them all and let me select what is viewable and what is not."
   - ALL plays are exported to Scott's side (on his computer).
   - Each play has a "Visible to players" on/off switch Scott can change at any time.
   - Publish sends ONLY the visible plays to the player app. Hidden plays are NOT shipped at all
     (not merely hidden in the UI), because anything shipped in a web app can be extracted.
   - Turning a play off and publishing again removes it from the app on next open.
7. Minors: no logins, no names, no analytics, no data collected. Optional team code.

## Play catalog (Scott, 2026-10-27)
8. "Fast Scout and Fast Draw are the same plays. Compare them both and extract all plays with no duplicates."
   Sources found (Claude Code, read-only check 2026-10-27):
   - Master: "Fast Scout Plays 2021-2022.pdf" (FastDraw export, 380 pages, vector, 0 images;
     copies at dist/docs/imports/ and uploads/bulk_imports/ x2, identical size 823318).
   - Category splits in C:\Users\scott\Documents\Basketball\Plays\{BLOB,Defense,Offense\Man,Offense\Zone,PressBreak,Transition}
     = "Pages from" the master (15+18+158+17+10+30 = 248 pages): subsets, not new plays.
   - "Patriots Playbook.pdf" (51 pages, creator react-pdf, a different app's export with a table of contents,
     "Phase N" frames and "Option" notes) — same plays in a different format; may have extra phases/options.
   - The program's database already holds 66 plays; 7 names repeat (1-2-2 x3; Triangle, Crush, Back, 41, 32, 1-Game x2).
     Some repeats may be legitimate (e.g. BLOB Triangle vs Offense Triangle).
   Rules: one entry per unique play (category + name, confirmed by drawing); every source listed per play;
   where two versions differ, keep both visible for Scott to choose; nothing in the database is deleted
   (deleting data is a Scott gate) — duplicates are only flagged.
9. Play entry should be interactive: the computer proposes the drawing from the PDF vectors, Scott confirms/fixes
   by clicking rather than drawing line by line. Scott's 14 hand-made plays (data/playbook/choreography/*.json)
   are the answer key to score the auto-draw.

## Drills (Scott, 2026-10-27)
10. "No drills. I think they are duplicate plays just named drills."
    EXCLUDE the master PDF's "Drills" section (206 pages) from the catalog.
    Vetter check (read-only): the Drills pages carry the same play names as the play sections (32-C, 41, 1-Game, Split, Triangle, ...);
    32 of 206 drill pages have a drawing identical to a play page, the rest are differently drawn versions of the same named plays.
    A few drill pages name other teams' plays ("RimRock | Varsity Man 1", "Victory | BLOB 1"). Scott 2026-10-27: do NOT include scouting plays ("They have different coaches and plays now").

## Carry improvements back to the main program (Scott, 2026-10-27)
11. "If / when I get the separated playbook operational to the way I want it, can you learn from it and apply it to the playbook in the main program?"
    Plan: when Scott approves the player app's look and movement, list every difference between static/js/player-viewer.js and
    templates/playbook.html (scripts/check_animation_sync.py shows the copied functions that changed); Hermes plans the port, the Vetter
    and Muse check it, OpenCode applies it on a branch, Scott merges. Long term: move the shared animation code into ONE file used by both
    (only after the animation is settled and the main playbook's behaviour is proven unchanged).

## Number-the-lines play entry (Scott, 2026-10-27)
12. "Can it be done without me drawing it? Number each line on each page and I tell you its order. Then you automate it."
    Vetter feasibility check (read-only demo, C:\Users\scott\Documents\Liberty_Play_Catalog\numbered_lines_DEMO.png, master pages 1-4):
    the FastDraw PDF holds every line as exact vector geometry; passes are dashed, cuts/moves solid, arrowheads filled.
    Problems seen in the existing extractor (playbook_vector_extract.py): page 1 lost player 3 (the inbounder stands above the
    baseline, outside the detected court box); arrowheads are counted as separate strokes; the ring drawn around the ball-handler
    is counted as a line; curved lines are reduced to straight chords (bezier curves not sampled); screens (T-foot) not separated.
    Scott's flow: show each sheet with its lines numbered; Scott types the order (e.g. "1, then 2+3 together, then 4"; or
    "4 is a screen"); the computer attaches each line to the nearest player, classifies pass/cut/dribble/screen from the PDF,
    and builds the choreography JSON (same format as data/playbook/choreography/*.json); Scott watches it animate and fixes only
    what is wrong. Score the auto-drawing against Scott's 14 hand-made plays.
    12b (Scott, 2026-10-27): "Number the squares so you know which square and line I am talking about... Or can you make them
    editable and I can just change the numbers and you automate them in order? How do I do moves that happen simultaneously?"
    Decision for the plan: every square (one diagram = one sheet / phase) gets a visible number S1, S2, ...; every line in it a
    number. Each line has a small EDITABLE order box pre-filled with the computer's guess; Scott changes the numbers and presses
    Play to check. SAME number on two lines = they move AT THE SAME TIME (e.g. 4 and 2 both "1" = both cut together, then the
    pass "2"). A line can also be set to "skip". Line type (pass/cut/dribble/screen) and player can be changed from a small menu
    next to the box. Typing "S2: 1, 2+3, 4" stays available as a shortcut. Nothing saves until Scott presses Save.

## View buttons and automatic defense (Scott, 2026-10-27)
12c. "Plus view/not view buttons?" -> each square/line gets show/hide; the player-app "Visible to players" switch per play
     already exists on the server side (Stage 1).
13. Automatic defense: "Zone defense is more showing responsibility areas based on ball location and shifting when offense moves.
    Basic standard rules for the zone defense are applied based on ball and player movement; I can move them around and the
    defense shifts accordingly. If I want to run it differently than the standard, I can add exceptions to the defensive
    placements, i.e. go over a screen, but mark when to go under a screen. Front a post, or not front a post."
    Design notes for Hermes (not yet planned): a rules engine, not drawing. Inputs: ball location + 5 offensive positions.
    Zone (2-3, 3-2, 1-3-1, ...): standard spot for each defender per ball region (corner, wing, top, high post, low post),
    blended as the ball moves; responsibility areas shaded. Man: defender between man and basket, sagging toward help side by
    distance from the ball. Scott drags offense or ball -> defense recomputes live. Exceptions: per defender, per situation,
    e.g. screen = over / under / switch (default + "under when <condition>"), post = front / 3-4 / behind; stored with the play.
    Existing code to reuse: man-defense helpers in templates/playbook.html (paintManDefenders, overlayPinnedDefense,
    playWantsManShell, syncLiveWithDefense). Answer key: the Defense section of the master PDF (1-3-1 "areas of
    responsibility", 2-3, 3-2, Man) — Scott's own diagrams of where defenders stand.
