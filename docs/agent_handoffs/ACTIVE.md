# Active Task

Updated: 2026-09-11  
Branch: `cursor/agent-os-ac1f`  
Base / default: `main` (= former `jason-5-may-updates` tip `05c8475`)

## Meta

| Field | Value |
| --- | --- |
| **id** | agent-os-and-simplify |
| **status** | `in_progress` |
| **executor** | cursor-only |

## Done (Proven)

- GitHub default branch set to **`main`**
- `main` fast-forwarded/forced to match former integration tip `05c8475`
- Living docs refreshed: `AUTHORITY.md`, `AGENT_PROTOCOL.md`, `docs/BRANCH_POLICY.md`, this `ACTIVE.md`
- Cursor rule updated to target `main`

## Next (in order)

1. Port Claude Film Review tools onto `main` via this branch (small commits): CI → migrate_paths → mark_stale → precision (opt-in)  
2. Branch inventory: keep vs delete list for Scott  
3. Layout tidy only after Scott OK per step  
4. Measured YOLO/OCR upgrades later (Adrian-first)

## Do not

- Schema / flags True / ball detector / unpause teach without Scott  
- Mass-delete branches without Scott’s list OK  
- Treat WSL Hermes dirty tree as source of truth  

## Report

### Proven
- `main` is default; docs + branch policy on `cursor/agent-os-ac1f`

### Inferred
- Fewer living docs + one active branch will stop work getting lost across tips

### Unknown
- Which remote `cursor/*` branches Scott wants deleted vs kept for reference
