# Active Task

Updated: 2026-08-09 (add/delete sticky roster)

Branch: `cursor/sticky-choreography-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | playbook-sticky-add-delete-player |
| **status** | `implemented` |
| **assigned_to** | cursor-agent |

## Decision (Scott)

On play detail / sticky choreography review, Scott must be able to **add** a missing offense token or **delete** an extra/wrong one when extract is wrong, then Save so Play All respects the edited roster.

## Approach

Stage 2 review chrome (same banner as Save choreography):

1. **＋ Add player** — next free `o1`–`o5` on the current sheet (prompt 1–5 to re-place if all present); writes `sheetAlignByStep` + step positions; marks dirty.
2. **× on token** — removes that offense id from **all** sheets’ align positions + sticky/session ink (paths/marks/passes), so carry-forward cannot resurrect it.
3. Persist via existing PUT `/api/playbook/choreography/<id>` → `data/playbook/choreography/{id}.json`.
4. View-mode sheet plays can drag tokens (choreography edit), not only editor mode.

Offense 1–5 only (defense still derived via man-mark offsets).

## Files

- `templates/playbook.html`
- `docs/playbook_sticky_choreography.md`
- `docs/agent_handoffs/ACTIVE.md`

## Verify

- Hard refresh sheet play → Add player / × visible beside Save choreography
- Add missing jersey → Save → reload → token still present; Play All includes it
- × extra token → Save → reload → token gone; Play All does not animate it
- Multi-team / Copy to / Rip / Triangle / Pitt5 / 1-Game unchanged aside from roster tools

## Report

### Proven

- Sticky JSON already stores sparse `positions` o1–o5; save path needed no schema change.
- UI wired: Add player + per-token ×; delete clears all steps so `positionsThrough` carry-forward cannot restore the oid.
- Drag listeners now attach in view mode when sheet choreography edit is allowed (previously editor-only).

### Inferred

- Deleting from all sheets is the right default for “extra extract token”; per-sheet-only tombstones were not needed for this slice.

### Unknown / remaining

- Scott visual sign-off on a play with a true missing/extra extract token.
- Path-handle editor + `.fdb` adapter (next slice).
- Defense token authoring (only if extract ever emits defense; not in sticky today).
