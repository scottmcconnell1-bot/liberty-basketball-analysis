"""Jersey number OCR from person bounding boxes."""

from __future__ import annotations

import os
import re

_OCR_ENGINE = None
_OCR_UNAVAILABLE = False
_PADDLE_ENGINE = None
_PADDLE_UNAVAILABLE = False


def ocr_packages_available() -> dict:
    """Fast check: is the OCR Python package installed (does not load ML weights)."""
    from helpers import module_available

    return {
        "easyocr": module_available("easyocr") and not _OCR_UNAVAILABLE,
        "paddleocr": module_available("paddleocr") and not _PADDLE_UNAVAILABLE,
    }


def jersey_ocr_engine_status() -> dict:
    """Report OCR backend availability without loading EasyOCR/Paddle weights."""
    packages = ocr_packages_available()
    return {
        **packages,
        "easyocr_loaded": _OCR_ENGINE is not None,
        "paddleocr_loaded": _PADDLE_ENGINE is not None,
    }


def _get_ocr_engine():
    global _OCR_ENGINE, _OCR_UNAVAILABLE
    if _OCR_UNAVAILABLE:
        return None
    if _OCR_ENGINE is not None:
        return _OCR_ENGINE
    try:
        import easyocr  # noqa: WPS433

        _OCR_ENGINE = easyocr.Reader(["en"], gpu=False, verbose=False)
        return _OCR_ENGINE
    except Exception:
        _OCR_UNAVAILABLE = True
        return None


def _get_paddle_engine():
    """Optional second OCR engine — often better on jersey digits when installed."""
    global _PADDLE_ENGINE, _PADDLE_UNAVAILABLE
    if _PADDLE_UNAVAILABLE:
        return None
    if _PADDLE_ENGINE is not None:
        return _PADDLE_ENGINE
    try:
        from paddleocr import PaddleOCR  # noqa: WPS433

        _PADDLE_ENGINE = PaddleOCR(
            use_angle_cls=False,
            lang="en",
            show_log=False,
            use_gpu=False,
        )
        return _PADDLE_ENGINE
    except Exception:
        _PADDLE_UNAVAILABLE = True
        return None


def _parse_jersey_text(text: str) -> tuple[int | None, float]:
    if not text:
        return None, 0.0
    digits = re.findall(r"\d{1,2}", text)
    if not digits:
        return None, 0.0
    candidates = []
    for token in digits:
        value = int(token)
        if 0 <= value <= 99:
            candidates.append(value)
    if not candidates:
        return None, 0.0
    best = candidates[0]
    confidence = 0.65 if len(candidates) == 1 else 0.45
    return best, confidence


def bbox_xyxy_from_center(cx: int, cy: int, width: int, height: int) -> tuple[int, int, int, int]:
    half_w = max(1, int(width) // 2)
    half_h = max(1, int(height) // 2)
    return int(cx) - half_w, int(cy) - half_h, int(cx) + half_w, int(cy) + half_h


def crop_torso(frame, x1: int, y1: int, x2: int, y2: int):
    """Upper ~45% of person bbox — jersey number region."""
    import cv2  # noqa: WPS433

    h, w = frame.shape[:2]
    x1 = max(0, min(x1, w - 1))
    x2 = max(0, min(x2, w))
    y1 = max(0, min(y1, h - 1))
    y2 = max(0, min(y2, h))
    if x2 <= x1 or y2 <= y1:
        return None
    torso_y2 = y1 + max(8, int((y2 - y1) * 0.45))
    crop = frame[y1:torso_y2, x1:x2]
    if crop is None or crop.size == 0:
        return None
    return crop


def crop_jersey_regions(frame, x1: int, y1: int, x2: int, y2: int):
    """Return multiple likely jersey-number crops (front chest + back/lower)."""
    import cv2  # noqa: WPS433

    h, w = frame.shape[:2]
    x1 = max(0, min(x1, w - 1))
    x2 = max(0, min(x2, w))
    y1 = max(0, min(y1, h - 1))
    y2 = max(0, min(y2, h))
    if x2 <= x1 or y2 <= y1:
        return []

    box_h = y2 - y1
    regions = []
    for start_pct, end_pct in ((0.0, 0.45), (0.30, 0.72), (0.55, 0.95)):
        ry1 = y1 + int(box_h * start_pct)
        ry2 = y1 + max(ry1 + 8, int(box_h * end_pct))
        crop = frame[ry1:ry2, x1:x2]
        if crop is not None and crop.size > 0:
            regions.append(crop)
    return regions


def _preprocess_variants(crop):
    """Return several preprocessed crops to improve digit readability."""
    import cv2  # noqa: WPS433

    variants = []
    if crop is None or crop.size == 0:
        return variants

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    denoised = cv2.fastNlMeansDenoising(enhanced, None, 8, 7, 21)

    for base in (enhanced, denoised):
        for scale in (2, 3):
            scaled = cv2.resize(
                base,
                None,
                fx=scale,
                fy=scale,
                interpolation=cv2.INTER_CUBIC,
            )
            variants.append(cv2.cvtColor(scaled, cv2.COLOR_GRAY2BGR))
            _, thresh = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            variants.append(cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR))

    return variants


def _read_with_easyocr(crop) -> tuple[int | None, float]:
    reader = _get_ocr_engine()
    if reader is None:
        return None, 0.0

    best_number = None
    best_conf = 0.0
    for variant in _preprocess_variants(crop):
        try:
            results = reader.readtext(
                variant,
                detail=1,
                paragraph=False,
                allowlist="0123456789",
                mag_ratio=1.5,
            )
        except Exception:
            continue
        for _bbox, text, conf in results:
            number, parsed_conf = _parse_jersey_text(str(text))
            if number is None:
                continue
            combined = float(conf) * parsed_conf
            if combined > best_conf:
                best_conf = combined
                best_number = number
    return best_number, best_conf


def _read_with_paddle(crop) -> tuple[int | None, float]:
    engine = _get_paddle_engine()
    if engine is None:
        return None, 0.0

    best_number = None
    best_conf = 0.0
    for variant in _preprocess_variants(crop)[:4]:
        try:
            results = engine.ocr(variant, cls=False)
        except Exception:
            continue
        if not results:
            continue
        for line in results:
            if not line:
                continue
            for item in line:
                if not item or len(item) < 2:
                    continue
                text = str(item[1][0])
                conf = float(item[1][1])
                number, parsed_conf = _parse_jersey_text(text)
                if number is None:
                    continue
                combined = conf * parsed_conf
                if combined > best_conf:
                    best_conf = combined
                    best_number = number
    return best_number, best_conf


def _pick_best_candidate(candidates, allowed_jerseys=None):
    if not candidates:
        return None, 0.0
    if allowed_jerseys:
        roster_matches = [
            (num, conf * 1.15)
            for num, conf in candidates
            if num in allowed_jerseys
        ]
        if roster_matches:
            return max(roster_matches, key=lambda item: item[1])
    return max(candidates, key=lambda item: item[1])


def read_jersey_from_bbox(
    frame,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    *,
    allowed_jerseys: set[int] | None = None,
) -> tuple[int | None, float]:
    """Return (jersey_number, confidence) from a person bounding box."""
    candidates = []
    regions = crop_jersey_regions(frame, x1, y1, x2, y2)
    if not regions:
        torso = crop_torso(frame, x1, y1, x2, y2)
        if torso is not None:
            regions = [torso]

    for crop in regions:
        easy_number, easy_conf = _read_with_easyocr(crop)
        if easy_number is not None:
            candidates.append((easy_number, easy_conf))
        paddle_number, paddle_conf = _read_with_paddle(crop)
        if paddle_number is not None:
            candidates.append((paddle_number, paddle_conf))

    best_number, best_conf = _pick_best_candidate(candidates, allowed_jerseys)
    if best_number is None:
        return None, 0.0
    return best_number, round(min(best_conf, 0.99), 3)


def read_jersey_from_detection(
    frame,
    cx: int,
    cy: int,
    width: int,
    height: int,
    *,
    allowed_jerseys: set[int] | None = None,
) -> tuple[int | None, float]:
    x1, y1, x2, y2 = bbox_xyxy_from_center(cx, cy, width, height)
    return read_jersey_from_bbox(frame, x1, y1, x2, y2, allowed_jerseys=allowed_jerseys)


def _detection_scope(db, game_id):
    from helpers import detection_scope_for_analysis

    return detection_scope_for_analysis(db, game_id)


def _roster_jersey_allowlist(db, game_id) -> set[int]:
    try:
        from analysis_helpers import get_analysis_roster_players

        payload = get_analysis_roster_players(db, game_id)
        allowed = set()
        for player in payload.get("players") or []:
            jersey = player.get("jersey_number")
            if jersey in (None, ""):
                continue
            allowed.add(int(jersey))
        return allowed
    except Exception:
        return set()


def _ocr_detection_targets(db, game_id, ai_settings=None) -> list[dict]:
    ai_settings = ai_settings or {}
    scope_sql, scope_params = _detection_scope(db, game_id)
    max_per_cluster = int(ai_settings.get("jersey_ocr_max_samples_per_cluster", 30))
    cluster_rows = db.execute(
        f"""
        SELECT DISTINCT player_cluster AS cluster_id
          FROM detections d
         WHERE {scope_sql}
           AND d.object_class = 'person'
           AND d.player_cluster IS NOT NULL
           AND d.player_cluster >= 0
         ORDER BY player_cluster
        """,
        scope_params,
    ).fetchall()

    targets = []
    seen = set()
    for cluster_row in cluster_rows:
        cluster_id = int(cluster_row["cluster_id"])
        rows = db.execute(
            f"""
            SELECT id, timestamp_ms, x_center, y_center, width, height
              FROM detections d
             WHERE {scope_sql}
               AND d.object_class = 'person'
               AND d.player_cluster = ?
             ORDER BY (d.width * d.height) DESC, d.confidence DESC
             LIMIT ?
            """,
            scope_params + (cluster_id, max_per_cluster),
        ).fetchall()
        for row in rows:
            key = (int(row["id"]), int(row["timestamp_ms"]))
            if key in seen:
                continue
            seen.add(key)
            targets.append({
                "detection_id": int(row["id"]),
                "timestamp_ms": int(row["timestamp_ms"]),
                "cluster_id": cluster_id,
                "x_center": int(row["x_center"]),
                "y_center": int(row["y_center"]),
                "width": int(row["width"]),
                "height": int(row["height"]),
            })
    return targets


def _run_ocr_targets(db, video_path, targets, allowed_jerseys=None) -> dict:
    import cv2  # noqa: WPS433

    if not targets:
        return {"ocr_attempts": 0, "updated": 0, "reads": 0}

    cap = cv2.VideoCapture(video_path, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        return {"skipped": True, "reason": "video_unreadable", "targets": len(targets)}

    frame_cache: dict[int, object] = {}
    reads = 0
    updated = 0
    try:
        print(f"[JerseyOCR] Scanning {len(targets)} player crops from video…")
        for index, target in enumerate(sorted(targets, key=lambda item: item["timestamp_ms"]), start=1):
            ts = target["timestamp_ms"]
            if ts not in frame_cache:
                cap.set(cv2.CAP_PROP_POS_MSEC, ts)
                ok, frame = cap.read()
                frame_cache[ts] = frame if ok else None
            frame = frame_cache.get(ts)
            if frame is None:
                continue

            jersey, conf = read_jersey_from_detection(
                frame,
                target["x_center"],
                target["y_center"],
                target["width"],
                target["height"],
                allowed_jerseys=allowed_jerseys,
            )
            reads += 1
            if jersey is None:
                continue

            db.execute(
                """
                UPDATE detections
                   SET jersey_read = ?, jersey_confidence = ?
                 WHERE id = ?
                """,
                (jersey, conf, target["detection_id"]),
            )
            updated += 1
            if index % 25 == 0:
                print(f"[JerseyOCR] Progress {index}/{len(targets)} — {updated} reads saved")
                db.commit()
        db.commit()
    finally:
        cap.release()

    print(f"[JerseyOCR] Finished — {updated} jersey reads saved from {reads} OCR attempts")
    return {"ocr_attempts": reads, "updated": updated, "targets": len(targets)}


def ocr_jerseys_on_cluster_samples(db, game_id, video_path, ai_settings=None) -> dict:
    """OCR the largest, clearest player bbox per court cluster."""
    ai_settings = ai_settings or {}
    if not video_path or not os.path.exists(video_path):
        return {"skipped": True, "reason": "no_video", "video_path": video_path}

    allowed = _roster_jersey_allowlist(db, game_id)
    targets = _ocr_detection_targets(db, game_id, ai_settings)
    result = _run_ocr_targets(db, video_path, targets, allowed_jerseys=allowed or None)
    result["skipped"] = False
    result["allowed_jerseys"] = sorted(allowed)
    return result


def _parse_cluster_id(player_value) -> int | None:
    if player_value is None:
        return None
    text = str(player_value).strip()
    if not text.isdigit():
        return None
    cluster_id = int(text)
    if cluster_id < 0:
        return None
    return cluster_id


def _sample_event_timestamps(events, max_per_cluster: int) -> dict[int, list[int]]:
    by_cluster: dict[int, list[int]] = {}
    for row in events:
        cluster_id = _parse_cluster_id(row["player"])
        if cluster_id is None:
            continue
        bucket = by_cluster.setdefault(cluster_id, [])
        if len(bucket) >= max_per_cluster:
            continue
        ts = int(row["timestamp_ms"])
        if not bucket or abs(bucket[-1] - ts) > 1500:
            bucket.append(ts)
    return by_cluster


def _best_detection_near_event(db, scope_sql, scope_params, cluster_id: int, timestamp_ms: int, window_ms: int):
    return db.execute(
        f"""
        SELECT id, timestamp_ms, x_center, y_center, width, height
          FROM detections d
         WHERE {scope_sql}
           AND d.object_class = 'person'
           AND d.player_cluster = ?
           AND d.timestamp_ms BETWEEN ? AND ?
         ORDER BY (d.width * d.height) DESC, d.confidence DESC
         LIMIT 1
        """,
        scope_params + (cluster_id, timestamp_ms - window_ms, timestamp_ms + window_ms),
    ).fetchone()


def ocr_jerseys_near_events(db, game_id, video_path, ai_settings=None) -> dict:
    """
    Re-read jersey numbers at event moments (±window) instead of random frame stride.

  Coaches can still fix unidentified players manually — this only improves reads where
  the player bbox is visible near a tagged event.
    """
    ai_settings = ai_settings or {}
    if not ai_settings.get("jersey_ocr_event_enabled", True):
        return {"skipped": True, "reason": "event_ocr_disabled"}
    if not video_path or not os.path.exists(video_path):
        return {"skipped": True, "reason": "no_video", "video_path": video_path}

    scope_sql, scope_params = _detection_scope(db, game_id)
    window_ms = int(ai_settings.get("jersey_ocr_event_window_ms", 3000))
    max_per_cluster = int(ai_settings.get("jersey_ocr_max_samples_per_cluster", 40))
    offsets_ms = ai_settings.get("jersey_ocr_event_offsets_ms") or [-2000, 0, 2000]

    from helpers import count_events_for_analysis
    from stats import _resolve_relational_game_id

    relational_game_id = _resolve_relational_game_id(db, game_id)
    event_count = count_events_for_analysis(
        db,
        analysis_key=str(game_id),
        relational_game_id=relational_game_id,
    )
    if event_count <= 0:
        return {"skipped": True, "reason": "no_events"}

    if relational_game_id is not None:
        events = db.execute(
            """
            SELECT player, timestamp_ms
              FROM events
             WHERE (relational_game_id = ? OR game_id = ?)
               AND source_type = 'ai'
               AND player IS NOT NULL
             ORDER BY timestamp_ms
            """,
            (relational_game_id, str(game_id)),
        ).fetchall()
    else:
        events = db.execute(
            """
            SELECT player, timestamp_ms
              FROM events
             WHERE game_id = ?
               AND source_type = 'ai'
               AND player IS NOT NULL
             ORDER BY timestamp_ms
            """,
            (str(game_id),),
        ).fetchall()

    samples_by_cluster = _sample_event_timestamps(events, max_per_cluster)
    if not samples_by_cluster:
        return {"skipped": True, "reason": "no_cluster_events"}

    targets = []
    seen = set()
    for cluster_id, timestamps in samples_by_cluster.items():
        for base_ts in timestamps:
            for offset in offsets_ms:
                ts = int(base_ts) + int(offset)
                det = _best_detection_near_event(
                    db, scope_sql, scope_params, cluster_id, ts, window_ms,
                )
                if det is None:
                    continue
                key = (int(det["id"]), int(det["timestamp_ms"]))
                if key in seen:
                    continue
                seen.add(key)
                targets.append({
                    "detection_id": int(det["id"]),
                    "timestamp_ms": int(det["timestamp_ms"]),
                    "cluster_id": cluster_id,
                    "x_center": int(det["x_center"]),
                    "y_center": int(det["y_center"]),
                    "width": int(det["width"]),
                    "height": int(det["height"]),
                })

    if not targets:
        return {"skipped": True, "reason": "no_detection_targets", "events_sampled": len(events)}

    allowed = _roster_jersey_allowlist(db, game_id)
    result = _run_ocr_targets(db, video_path, targets, allowed_jerseys=allowed or None)
    result.update({
        "skipped": False,
        "events_sampled": sum(len(v) for v in samples_by_cluster.values()),
        "clusters": len(samples_by_cluster),
        "allowed_jerseys": sorted(allowed),
    })
    return result


def ocr_jerseys_for_game(db, game_id, video_path, ai_settings=None) -> dict:
    """Run full jersey OCR scan: largest cluster crops, then event-window crops."""
    ai_settings = ai_settings or {}
    if not video_path or not os.path.exists(video_path):
        from analysis_helpers import resolve_analysis_game_context

        context = resolve_analysis_game_context(db, game_id)
        video_path = context.get("video_path")
    if not video_path or not os.path.exists(video_path):
        return {"skipped": True, "reason": "no_video", "video_path": video_path}

    print(f"[JerseyOCR] Starting full jersey scan for {game_id}")
    cluster_result = ocr_jerseys_on_cluster_samples(db, game_id, video_path, ai_settings)
    event_result = ocr_jerseys_near_events(db, game_id, video_path, ai_settings)
    from helpers import count_jersey_reads_for_analysis

    return {
        "skipped": False,
        "video_path": video_path,
        "cluster_scan": cluster_result,
        "event_scan": event_result,
        "ocr_read_count": count_jersey_reads_for_analysis(db, game_id),
    }
