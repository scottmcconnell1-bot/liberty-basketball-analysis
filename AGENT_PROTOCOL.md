# Agent Protocol — Cursor Only

Updated: 2026-09-11  
Default branch: `main`

## Authority order

When sources disagree:

1. Scott’s current instruction  
2. Files on the active branch (`AUTHORITY.md`, this file, `ACTIVE.md`)  
3. Git history / remote state  
4. Tests and runtime logs  
5. Other docs  
6. Agent analysis  
7. Chat memory (never truth)

## Session start

1. `git remote -v` and `git branch --show-current` — confirm Liberty repo  
2. Read `AUTHORITY.md` and `docs/agent_handoffs/ACTIVE.md`  
3. Prefer **Composer/Auto**; one bounded slice per session  

## Change cycle (optimized)

1. **Recommend** — what, why, how you’ll verify (plain language)  
2. **Wait** for Scott’s explicit OK  
3. **Implement** the smallest change  
4. **Verify** (tests / Flask 200 / import)  
5. **Update ACTIVE** and show results before the next step  

Use `git mv` for renames. Do not run ahead across multiple structural moves.

## Isolation

Liberty work only. No other projects’ data, credentials, or status in this repo’s replies.

## Tools policy

- Prefer **current measured** tools on/near `main` (opt-in precision events, path migrate, stale-run marker, CI).  
- Upgrade YOLO/OCR only with a before/after on a fixed clip set and Scott’s OK.  
- Do not treat a second clone (e.g. WSL Hermes tree) as truth.
