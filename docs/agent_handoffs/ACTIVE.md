# Active Task

Updated: 2026-09-14 (dual-machine roles locked + home bring-up verified)

Branch: `cursor/film-tool-review-layout-ac1f`  
Related: `cursor/full-stack-bringup-ac1f` / PR #147 = auto-accept unlock (**Scott gate — do not merge unless asked**)

## Dual-machine roles (locked)

| | **Home** | **School / remoted Cursor** |
| --- | --- | --- |
| `film_analysis.db` + `uploads/` | **Source of truth** (~14.5 GB + ~106 GB) | Empty — **never** copy school DB onto home |
| Full app / reanalyze / teach | Run here | Use Funnel only |
| Coach / walkthrough | Local or Funnel | Funnel → home |
| Code / docs / PRs | git pull → work → push | Same |
| Shared brain | GitHub + this `ACTIVE.md` | Same — **not** two databases |

Funnel (home): https://liberty-coach.tail368a37.ts.net → `:8080`  
School handoff note: `docs/agent_handoffs/HOME_PC_HANDOFF.md` on `origin/cursor/full-stack-bringup-ac1f`

## Current product focus

| Field | Value |
| --- | --- |
| **id** | adrian-accuracy-quality |
| **status** | `in_progress` (infra ready; resume film review) |
| **scope** | **Adrian JrHigh only** until Scott says accurate |
| **game** | `jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334` |

## Home verified (Proven)

- DB / uploads / Flask `:8080` / `/coach` / Funnel all live
- Overlay fix, tip_off, steal-vs-rebound already on this Film Tool branch

## Try (next best step)

1. On **home**: Film Tool → Show ledger → tip_off ~3.3s; steal ~13s (not rebound @ ~11s)
2. From **school**: open Funnel URL (hits home data) — do not rebuild the library
3. One feature branch at a time — stay on Film Tool for Adrian; leave #147 alone unless Scott unlocks auto-accept

## Do not

- Restore empty school DB over home
- Unpause teach loop / flip auto-accept without Scott
- Dual-merge Film Tool + full-stack blindly
- Sync DBs/uploads via git
