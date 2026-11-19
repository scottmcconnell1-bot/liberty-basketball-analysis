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
