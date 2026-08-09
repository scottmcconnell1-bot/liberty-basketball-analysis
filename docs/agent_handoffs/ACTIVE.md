# Active Task

Updated: 2026-08-09 (dash-based pass/cut + start attribution)

Branch: `cursor/sticky-choreography-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | playbook-vector-dash-pass-cut |
| **status** | `implemented` |
| **assigned_to** | cursor-agent |

## Decision (Scott)

Infer pass/cut from FastDraw stroke style (`dashes`), not tip-near-digit. Attribute mover/passer by stroke **start** endpoint; receiver by **end**. This PDF’s Proven encoding may invert Scott’s typical dash=cut / solid=pass convention — follow the PDF.

## Approach

1. `_has_dash_pattern` → pass; solid `[]` → cut; fill path → dribble (unchanged).
2. Start snap 60 (cut) / 75 (dashed pass) — recovers Rip p122 @66.7.
3. Orient: PDF order when start hits; reverse only if start misses and end hits.
4. Tests on Rip / 1-Game / Triangle / Pitt; vector audit README encoding verdict + Q3/Q4.

## Files

- `playbook_vector_extract.py`
- `tests/test_playbook_vector_extract.py`
- `docs/playbook_vector_audit/README.md`
- `data/playbook/vector_audit/README.md`
- `docs/agent_handoffs/ACTIVE.md`

## Verify

- Hard refresh playbook / sheet extract — Triangle & Pitt must not invent solid passes
- Rip p120 / 1-Game p32 still show dashed passes
- Rip p122 dashed stroke attributes (o4 pass path)

## Report

### Proven

- This Fast Scout PDF: dashed=`[5.25 5.25] 0` → pass; solid=`[] 0` → cut; fill → dribble (Rip/1-Game/Triangle/Pitt samples).
- Scott’s typical dash=cut / solid=pass is **inverted** vs this export.
- tip≠start classification removed; Triangle only keeps dashed o1→o2; Pitt has zero invented passes.
- Rip p122 dashed start o4@66.7 attributed with radius 75.

### Inferred

- FastDraw path order on samples is passer→receiver for dashed strokes.

### Unknown / remaining

- Whether every dashed stroke in the full book is a pass when tip misses digits.
- Path-handle editor + `.fdb` adapter (next slice).
