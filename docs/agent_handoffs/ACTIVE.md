# Active Task

Updated: 2026-08-10 (videos ACTIONS UI readable)

Branch: `cursor/videos-actions-ui-ac1f`  
Base: `jason-5-may-updates`

## Meta

| Field | Value |
| --- | --- |
| **id** | videos-actions-ui |
| **status** | `done` |
| **assigned_to** | cursor-agent |

## Scope delivered

- `/videos` ACTIONS: primary **Film Tool / Review / Archive|Unarchive** always visible
- Secondary actions under in-flow **More** (Results, Load counts, Rebuild, Re-run AI, Trim, Compare, Debug, Delete)
- Larger hit targets, high-contrast button text, sticky Actions column + horizontal scroll (no clipped labels)

## Try

1. Hard-refresh `https://liberty-coach.tail?.ts.net/videos` (or local `:8080/videos`)
2. Confirm primary buttons readable; open **More** for full secondary labels
3. Archive view shows **Unarchive** as primary

## Report

### Proven

- Template-only change in `templates/videos.html`

### Inferred

- Clip was from many `btn-sm` in one wrap row + global `.btn { overflow:hidden; max-width:100% }`

### Unknown

- Whether Scott prefers More collapsed by default long-term vs always-expanded second row
