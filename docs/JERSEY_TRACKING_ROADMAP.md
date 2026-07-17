# Jersey OCR + Stable Tracking Roadmap

**Priority:** P0 — this is the core product promise: automated per-player stats tied to jersey numbers.

**Current state (before this work):** YOLO detects people → unstable inline tracker → KMeans court slots (Pos 0–9) → heuristic events → **manual** coach mapping to roster.

**Target state:** Stable track IDs across frames → jersey number read from video → auto-link to roster → events and box score attributed to `#12 Name` without manual mapping.

---

## Architecture (target)

```
Video
  → Person detection (YOLO)
  → Multi-object tracking (ByteTrack via Ultralytics)
  → Jersey OCR on upper-torso crop (per track, every N frames)
  → Vote aggregation: tracker_id → jersey_number (+ roster match)
  → Event pipeline uses track_id at possession time → player label
  → Box score / minutes / shot breakdown by jersey
```

---

## Phases

### Phase 1 — Foundation (this PR)

| Deliverable | Status |
|-------------|--------|
| `tracker_backend=bytetrack` in `ai_analyzer.py` (Ultralytics `model.track`) | Implemented |
| `detections.jersey_read`, `jersey_confidence` columns | Implemented |
| `jersey_ocr.py` — torso crop + OCR (EasyOCR when installed) | Implemented |
| `track_identity.py` — vote aggregation cluster/track → jersey | Implemented |
| Settings: `jersey_ocr_enabled`, `auto_apply_jersey_mapping`, thresholds | Implemented |
| Auto-apply high-confidence OCR → events via `court_slot_mapping` | Implemented |
| `GET /api/track-identity/<game_id>` — suggestions + applied labels | Implemented |
| Fix `frame_stride` / `detection_stride` wiring | Implemented |

**Phase 1 limitation:** Events still originate from spatial clusters; jersey labels are applied **after** event generation by mapping cluster ↔ jersey votes from co-occurring detections. Good enough for first automated box scores; not yet track-native events.

### Phase 2 — Track-native events (in progress)

| Deliverable | Status |
|-------------|--------|
| `build_possession_segments()` prefers `tracker_id` when track lifespan ≥ 15 frames | Implemented |
| `events.player` = jersey label from `track_identity_labels` at event timestamp | Pending |
| Deprecate KMeans cluster as primary identity (keep as fallback) | Partial — tracker preferred when stable |
| Substitution detection: track ID change on court slot | Pending |

### Phase 3 — Accuracy hardening

- Custom jersey digit model trained on NFHS angles (Liberty uniform colors)
- Higher inference resolution (`imgsz=1280`) option for varsity film
- Lineup at tip-off seed + bench track re-entry heuristics
- Confidence-gated review queue (auto-accept ≥0.85, coach review 0.5–0.85)

### Phase 4 — Full automation UX

- Analysis results show per-jersey stats with no mapping step
- Film Tool AI events pre-labeled with jersey
- Official vs preview stats (review workflow unchanged)

---

## Settings reference

| Key | Default | Purpose |
|-----|---------|---------|
| `tracker_backend` | `bytetrack` | `bytetrack`, `inline` (legacy greedy) |
| `detection_stride` | `1` | Process every Nth frame |
| `jersey_ocr_enabled` | `true` | Run OCR on person crops |
| `jersey_ocr_stride` | `5` | OCR every Nth person-detection frame per track |
| `jersey_ocr_min_confidence` | `0.55` | Minimum OCR confidence to count a vote |
| `auto_apply_jersey_mapping` | `true` | Auto-rewrite events when cluster→jersey confidence high |
| `identity_auto_apply_min_confidence` | `0.70` | Minimum vote confidence to auto-apply |
| `identity_auto_apply_min_samples` | `8` | Minimum OCR reads per cluster before auto-apply |

---

## Dependencies

- **Required:** `ultralytics` (includes ByteTrack tracker configs)
- **Optional:** `easyocr` for jersey OCR (`pip install easyocr` on AI workstation)
- Without EasyOCR, jersey OCR returns no reads (tracking still upgrades)

---

## Success metrics (Phase 1)

On a single trimmed regulation game:

1. Median track lifespan > 30 frames (vs ~2 today)
2. ≥ 6 of 10 roster players get OCR jersey suggestion with confidence ≥ 0.5
3. Box score shows jersey labels without manual mapping on ≥ 50% of players
4. Coach review queue < 20% of scoring events flagged low-confidence

---

## Files

| File | Role |
|------|------|
| `ai_analyzer.py` | Detection + ByteTrack + jersey OCR write |
| `jersey_ocr.py` | Crop + OCR |
| `track_identity.py` | Vote aggregation, auto-apply |
| `court_slot_mapping.py` | Event relabel (reused) |
| `event_generator.py` | Phase 2: track-native segments |
| `blueprints/ai.py` | `/api/track-identity` |
