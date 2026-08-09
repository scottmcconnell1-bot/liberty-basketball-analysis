# Sticky play choreography (authoritative model)

Updated: 2026-08-09

## Why competitors feel better

CoachCanvas, HoopCoach Playbook, and Basketball Tactic Board **author** plays as
vector steps (player tokens + movement paths / frames). Import means FastDraw
`.fdb`, proprietary tactic files, or redraw — not OCR of a printed PDF.

Liberty imports coach PDF/PNG sheets and **guesses** digit centers + ink
polylines on every Play All. That is why Rip / 1-Game still drift: OCR ≠ native
play JSON.

## Upgrade path (this slice)

1. OCR / ink remain the **draft** proposer.
2. Sticky JSON at `data/playbook/choreography/{play_id}.json` becomes the
   **authoritative** model once Scott saves.
3. Play All prefers sticky positions + outbound ink; Skip OCR until Reset.

### JSON shape

```json
{
  "version": 1,
  "play_id": 98,
  "sticky": true,
  "source": "user_save",
  "steps": [
    {
      "step_index": 0,
      "source_image": "/uploads/...",
      "court_frac": {},
      "positions": { "o1": { "x": 0, "y": 0 } },
      "ink": { "paths": {}, "marks": {}, "passes": [] }
    }
  ]
}
```

No `schema.sql` change (same pattern as `team_key` / sheet_align_cache).

### How Scott uses it

1. Open a sheet play → wait for Ready (OCR or sticky).
2. Drag tokens to match PDF spacing.
3. Optional: ▶ Play All once (captures ink paths into the session).
4. Click **Save choreography**.
5. Hard refresh — banner says “saved choreography”; Play All reuses it.

**Reset OCR** deletes the sticky file and re-runs digit/ink detection.

## Next slice (suggested)

Lightweight path editor (drag polyline handles / redraw one cut) so sticky ink
can be corrected without re-OCR, plus optional FastDraw `.fdb` import adapter
if Scott has a library to migrate.
