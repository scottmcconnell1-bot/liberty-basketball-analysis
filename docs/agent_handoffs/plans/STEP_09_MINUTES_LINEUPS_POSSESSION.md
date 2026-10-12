# Step 9 — Minutes, lineups, and one possession record

Read `00_INDEX.md` first. Source of scope: `PROGRAM_FOR_JASON_2026-10-10.md` section 6, step 9 and section 4, items 5 and 6.

**Owner:** Cursor. **Depends on:** Step 8. **Blocks:** Step 10.
**This step may need a `schema.sql` change, which is a Scott gate.** Find out early and ask before writing.

## Do not start this step early

The program file is blunt about this one: **do not build plus/minus on a ledger that has the wrong shots.** Minutes and lineups multiply whatever error is in the ledger across every player on the floor.

## Two targets

1. **Minutes and lineups** from substitutions Scott trusts.
2. **One possession record** that the film room, the box score, and scouting all read.

## On the possession gap — read this before believing the June audit

The June 2026 gap audit (`docs/BASE_PLATFORM_GAP_AUDIT.md`) said there was no possession table. The program file says to treat that audit as history for auth, but that the possession gap is still real.

Checked 2026-10-11, the picture is more specific than "no table":

- A **`possessions` table exists** in `schema.sql:306`, with `game_id`, `team_id`, `period`, start and end timestamps, `start_event_id`, `end_event_id`, `outcome`, `points_for`, `source`, `review_status`, `confidence`.
- `events` already carries a `possession_id` foreign key (`schema.sql:80`, and again at `:423`).
- It is **written** by `helpers.py:2079` (`INSERT INTO possessions`) and **read** by `stats.py` (lines 694, 729, 747, 762, 768, 795), `playbook_play_match.py:541`, and `blueprints/clips.py:153`.
- Meanwhile the film pipeline builds its own possession segments in memory — `build_possession_segments` (`event_generator.py:455`), `find_ball_possession` (`:93`), `_merge_short_segments` (`:738`) — and those are what the shot pass actually uses.

So the gap is **not a missing table**. It is that the film pipeline's segments and the `possessions` rows are two different records of the same thing.

**Confirmed by Scott on the home machine, 2026-10-11:** the table already exists (`schema.sql:306`) and `helpers.py:2079` writes it, while the film shot pass still builds its segments in memory. This step maps which screen reads which record. **It does not create a second table.** A schema change is still a Scott gate, and `scripts/check_scott_gates.py` will refuse a pull request that touches `schema.sql` without naming it.

Establishing which record each module actually reads is the first task of this step.

## Where the code is

| Symbol | File:line | Role |
| --- | --- | --- |
| `backfill_player_minutes` | `player_minutes.py:26` | |
| `get_player_minutes` | `player_minutes.py:115` | |
| `backfill_all_games` | `player_minutes.py:94` | |
| `load_starters` / `save_starters` | `game_lineups.py:105` / `:128` | Starters live in a file, not the database |
| `lineup_path` | `game_lineups.py:33` | |
| `jersey_set` | `game_lineups.py:143` | |
| `build_possession_segments` | `event_generator.py:455` | In-memory film segments |
| `find_ball_possession` | `event_generator.py:93` | |
| `possessions` table | `schema.sql:306` | The database record |
| `events.possession_id` | `schema.sql:80`, `:423` | The join that already exists |
| `helpers.py:2079` | — | The only writer found |
| `tests/test_game_lineups.py` | — | Existing tests |

## The work

1. **Map the data first.** For each of the film room, the box score, scouting, the playbook, and clips: which possession record does it read today — the in-memory segments, the `possessions` table, or neither? Write it down. The protocol requires this before changing a save path.
2. **Decide the single record** with Scott, once the map exists. If this needs a `schema.sql` change, stop and ask — it is a gate.
3. **Minutes from substitutions Scott trusts.** Not from detection presence alone. Say where the substitution signal comes from and how he confirms it.
4. **Lineups** on top of minutes. Note that starters currently live in a JSON file (`game_lineups.py:33`), not the database — reconciling that with the one-record goal is part of this step.
5. **Plus/minus last, or not at all this step.** It is the most error-sensitive number in the app and the program file names it specifically.

## Exit test

- A written map of which module reads which possession record, verified by running each module, not by reading code.
- One possession record that the film room, the box score, and scouting all read. No second database.
- Minutes computed from substitutions Scott trusts, checked against at least one game he can confirm.
- Lineups follow from those minutes.

## Do not, on this step

- Do not build plus/minus on a ledger that has the wrong shots.
- Do not change `schema.sql` without asking. Scott gate.
- Do not grow a second database. One ledger is the product.
- Do not start from the June audit's conclusions. Verify current state first.
- Do not reorganize the core sequence.

## Hand off with

Proven / Inferred / Unknown, the module-to-record map, the schema decision (and Scott's answer if a gate was hit), and the `ACTIVE.md` edit.
