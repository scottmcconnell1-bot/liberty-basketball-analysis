# Archive: playbook-1-game-choreography

Updated: 2026-08-08
Superseded by: playbook-1-game-pass-polish (pass overshoot fix)

## Summary

Initial 1-Game (play 98, pages 32–36) Scott sequence wiring:
`apply_game_sequence_routes` + `seed_game_sheet_positions`, frontend
`isGamePlay` / `orderGameBeats` / `ensureGameBeats`, cache v11.

Beat list mapped to Scott steps (pops → screen 1→4 → reverse passes →
downscreen → finish on right block). Clean court; no Rip/Triangle/Pitt 5 regression.

Remaining after that slice: Scott reported passes overshooting the receiver
(addressed in the follow-on polish).
