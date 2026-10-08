# Agent Protocol

Updated: 2026-10-07  
Default branch: `main`

## Authority order

When sources disagree:

1. Scott's current instruction  
2. Files on `main` (`AUTHORITY.md`, this file, `ACTIVE.md`)  
3. Git history / remote state  
4. Tests and runtime logs  
5. Other docs  
6. Agent analysis  
7. Chat memory (never truth)

## Session start

1. `git remote -v` and `git branch --show-current` — confirm the Liberty repo  
2. Read `AUTHORITY.md` and `docs/agent_handoffs/ACTIVE.md` (about 8 KB together; the old ACTIVE text is in `ARCHIVE/`)  
3. Prefer Composer/Auto; one bounded slice per session  

## Change cycle

1. **Say what and why**, then do it when Scott has asked for it. Wait for his OK only for the gates in `AUTHORITY.md` and for edits to the protected core files.
2. **Implement** the smallest change.  
3. **Verify against the real thing**: run it, query it, load the live page. A passing unit test alone is not verification.  
4. **Update `ACTIVE.md`** by replacing the paragraph it changes. Do not stack a new "Proven" paragraph on top of an old one that it contradicts. Move old text to `ARCHIVE/`.

Use `git mv` for renames. Do not run ahead across multiple structural moves.

## A message sent during a job

It is added instruction. Finish the job already underway and include the new instruction in the same job. Stop only when Scott says stop, drop, or switch. Report the original job and what the added instruction changed in one place.

## Before changing a save path or a tool people type into

- Write down where each piece of data lives (browser, server file, database) and which code moves it from one to the next.
- After the change, confirm the data reached the server: read the server's copy back. A browser-only copy is not saved.
- Time the action with the real data size. The film tool tag table has 378 rows.

## Isolation

Liberty work only. No other projects' data, credentials, or status in this repo's replies.

## Tools policy

- Prefer current measured tools on or near `main` (opt-in precision events, path migrate, stale-run marker, CI).  
- Upgrade YOLO/OCR only with a before/after on a fixed clip set and Scott's OK.  
- Do not treat a second clone (e.g. WSL Hermes tree) as truth.
