<!--
Delete the parts that do not apply. Keep the Score block if this pull request changes
how a shot is read -- the guardrails job blocks it otherwise.
-->

## What changed and why

## Score

<!--
Required when this touches net_detector.py, event_generator.py, ai_bridge.py,
stat_rules.py, manual_tag_teach.py, ai_analyzer.py or court_memory.py.

Run it, do not estimate it:
    python scripts/shot_tag_score.py --game-id "<run key>" --fixture adrian_111

Paste the line. A note that says a rule is implemented is not a result.
-->

right=? makes_missed=? misses_called_makes=? of ? tags

Floor: 85 / 20 / 6 on the 111 tags. Calling every shot a miss scores 73, so a number
near 73 is not progress. If the score is below the floor, say so and say what you
learned -- a failed attempt that is written down is worth more than one that is retried.

## Report

<!-- From AUTHORITY.md. Chat memory is not repository truth. -->

### Proven
<!-- A command, a query, a file or a frame was checked in this session. Say which.
     A passing unit test alone is not verification of a film fix. -->

### Inferred

### Unknown

## Scott gates

<!--
One line per gate crossed, or delete this section. The guardrails job checks for it:

    Scott approved: schema.sql — adds the possession index, he said yes 2026-10-11

Gates: schema.sql, models/, a feature flag going False to True, ball_confidence,
ball_detector_model, auto_accept_event_confidence, the 80 and 170 rise gates,
make_min_gap_frames, emit_fouls, unpausing teach or auto-accept, deleting data.
-->

## Checks

- [ ] `pytest tests/` — said which failures are pre-existing on `main`, if any
- [ ] Nothing from the Shared drive folder is committed (`.env`, the database, the films, `data/film_tags/`)
- [ ] If this is for Jason, the matching `Brad/Claude` pull request is open (`docs/BRANCH_POLICY.md` rule 3)
