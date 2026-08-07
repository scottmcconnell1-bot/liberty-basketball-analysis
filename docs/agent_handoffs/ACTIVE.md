# Active Task

Updated: 2026-08-06 (teach tool verdict + hung restart + panel-first)

Branch: `cursor/full-film-panel-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | teach-tool-hung-panel-priority |
| **status** | `implemented` (ops healthy; hung+panel-first shipped; Rimrock advancing) |
| **assigned_to** | cursor-agent |

## Objective

Scott asked: best teaching tool? Can we do better? Fix hung ops without approval; align curriculum to full-film panel gates.

## Verdict (chat-ready)

**Best available tool in-repo for panel gates: `scripts/hoops_teach_loop.py`** (orchestrator), not a replacement.

| Tool | Role vs panel goal |
| --- | --- |
| `hoops_teach_loop` | **Primary** — analyze → teach → regenerate-all → score → panel |
| `teach_from_hoops_pbp` | Teaching signal for Hoops/panel games (called by loop) |
| `teach_from_boxscore` | Caps for HUDL/team totals (called by loop) |
| Manual analyze API / one-off scripts | Ops only — no curriculum |
| Devin / parallel cloud VMs | Out of scope (Cursor Pro only) |

Gaps that mattered: (1) hung GPU workers sat forever, (2) queue was Hoops-list then HUDL FIFO — not worst panel recall first. Mid-film resume still absent (full re-queue after fail).

## Live health (Proven @ session)

- Flask `:8080` alive; teach loop restarted onto new code; **Rimrock launcher advancing** (detections growing) — **not killed**.
- Per-game zombie reclaim live: **36** stuck runs cleared while Rimrock ran.
- Panel still **FAIL** (P≈70.6% R≈52.6%; score/points exact 0%).

## Shipped this slice

1. **Hung-launcher auto-restart** — same `progress_pct|step` for ≥45m (`LIBERTY_HUNG_STALE_SEC`) → kill that key’s PID only → mark failed → re-queue.
2. **Panel-first curriculum** — fixed panel bases, worst recall first, ahead of HUDL FIFO.
3. **`scripts/teach_ops_status.py`** — one-shot status + optional LEARNING_STATUS refresh.
4. Tests: `tests/test_hoops_teach_reclaim.py` (**8 passed**).
5. Docs: `TEACH_LOOP_SURVIVAL.md`, this handoff.

## Recommended path forward

1. Keep **`hoops_teach_loop`** as the overnight driver (watchdog installed).
2. Let hung restart + reclaim prevent silent idle; do not babysit restarts.
3. After more teaches, watch panel: Idaho City / Melba / Camas recall are the largest holes.
4. Next engineering (optional): mid-film resume; panel-only re-teach cadence when HUDL queue is long but panel still FAIL.

## Report

### Proven

- Rimrock live + advancing; teach wait logs show reclaim + `[wait]`.
- `hoops_teach_loop` is the only end-to-end panel pipeline in-repo.
- Hung + panel-first tests pass; teach restarted with new code (GPU left alone).

### Inferred

- More HUDL film still helps boxscore caps, but panel P/R is dominated by Hoops PBP teach + regenerate on the six panel keys.
- 45m hung threshold is safe for healthy frame-advancing jobs.

### Unknown

- Exact North Star launcher exit cause earlier today.
- Whether mid-film resume is worth the risk vs full re-queue.
