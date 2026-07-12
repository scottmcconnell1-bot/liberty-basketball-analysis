# External CV reference repos (not part of Liberty)

## Abdullah Tarek `basketball_analysis`

| Field | Value |
|-------|-------|
| Upstream | https://github.com/abdullahtarek/basketball_analysis |
| Liberty relation | **Reference only** — not a dependency, submodule, or fork |
| Who cloned it | Hermes/Rex agent on the `monk-admin` Linux host |
| When | **2026-07-12** (~09:47 local) during a side-by-side comparison requested in chat |
| Why | Compare offline CV techniques (CLIP team colors, possession stubs, drawers) vs Liberty's Flask workflow |
| Installed by Liberty code? | **No** — no script in this repo clones Abdullah's project |

Liberty already had its own models (`models/court_keypoint_detector.pt`, `models/ball_detector.pt`, etc.), ByteTrack, EasyOCR jersey pipeline, and SQLite-backed detections before that comparison.

## What we adopted (surgical ports)

| Technique | Liberty module | Notes |
|-----------|----------------|-------|
| Ball containment + temporal possession filter | `ball_possession.py` → `event_generator.py` | Distance-only possession was too flickery |
| Stable `tracker_id` for segments | `event_generator.build_possession_segments()` | Phase 2 of `JERSEY_TRACKING_ROADMAP.md` |
| CLIP team-color classifier | **Not adopted** | Liberty targets jersey **digits** → roster names |
| Abdullah folder layout / stub files | **Not adopted** | SQLite detections are the cache layer |

## Removing the reference clone from `monk-admin`

This repo does not control the server. On the Linux host:

```bash
bash scripts/remove_external_cv_reference_repos.sh
```

Or manually:

```bash
rm -rf /home/monk-admin/PROJECTS/abdullahtarek_basketball
```

Keep `/home/monk-admin/PROJECTS/liberty-basketball-analysis` — that is the product repo.

## Access

Abdullah Tarek does **not** own `scottmcconnell1-bot/liberty-basketball-analysis`. Collaborator access is optional and unrelated to the reference clone.
