# Active Task

Updated: 2026-07-23
Branch: `cursor/playbook-auto-digitize-ac1f` (worktree `C:\Users\scott\Documents\liberty-digitize-wt`)

## Meta

| Field | Value |
| --- | --- |
| **id** | playbook-auto-digitize |
| **status** | `completed` |
| **assigned_to** | cursor-agent |

## Report

### Proven

- Built `playbook_digitize.py`: OpenCV CC + EasyOCR crop OCR + offense template backup; maps Fast Scout PNGs (basket at image top) → SVG `500×470` with Y-flip; keys `o1`–`o5` / `d1`–`d5`.
- CLI: `py -3.12 scripts/digitize_playbook_plays.py --play-id N --write` or `--all --write`.
- API: `POST /api/playbook/play/<id>/digitize`, `POST /api/playbook/digitize-all`; Playbook UI **Digitize** / **Digitize all**.
- Batch wrote positions for **59/63** image-only plays (55 this batch + 4 earlier samples). Still empty: plays **8, 30, 36, 38** (sparse/low-conf — skipped, not invented).
- Proof play **2** (`1-Game`): 5 steps with `o1`–`o5`; step 0 vs 1 positions differ so Play All lerp moves tokens.
- Offense plays emit O only; defense plays emit D only (category prefer).
- Unit tests: `tests/test_playbook_digitize.py` (6 passed).
- Did not change `schema.sql`, feature flags, or ball detector. Did not kill analysis_launcher / hoops_teach_loop.

### Inferred

- Remaining 4 fails are odd pages (few/no readable markers). Manual Edit still works.
- Arrow → `movements_json` not implemented yet; positions alone unlock smooth Play All lerp.
- Live `:8080` may still be the dirty film-tool branch; digitize **DB writes** apply immediately; Digitize **button** needs server running worktree/branch code.

### Unknown

- Whether Scott wants arrow/cut digitization in a follow-up.
- Exact court-frame calibration quality on every PDF page (some formations may need manual nudge).

### How to run

```bat
cd C:\Users\scott\Documents\liberty-digitize-wt
py -3.12 scripts/digitize_playbook_plays.py --list
py -3.12 scripts/digitize_playbook_plays.py --play-id 2 --write --force
py -3.12 scripts/digitize_playbook_plays.py --all --write
```

Click path: Playbook → **1-Game** (id 2) → **Play All** (tokens should glide). **Edit** → **Digitize** after server is on this branch.

### Changes

- `playbook_digitize.py` — detector
- `scripts/digitize_playbook_plays.py` — batch CLI
- `blueprints/playbook.py` — digitize API routes
- `templates/playbook.html` — Digitize buttons; only render existing position keys; Play All lerp across present ids
- `tests/test_playbook_digitize.py`
- DB: `positions_json` filled for ~59 imported plays
