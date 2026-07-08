"""Jersey number OCR from person bounding boxes."""

from __future__ import annotations

import os
import re

_OCR_ENGINE = None
_OCR_UNAVAILABLE = False
_PADDLE_ENGINE = None
_PADDLE_UNAVAILABLE = False


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


def read_jersey_from_bbox(frame, x1: int, y1: int, x2: int, y2: int) -> tuple[int | None, float]:
    """Return (jersey_number, confidence) from a person bounding box."""
    crop = crop_torso(frame, x1, y1, x2, y2)
    if crop is None:
        return None, 0.0

    candidates = []
    easy_number, easy_conf = _read_with_easyocr(crop)
    if easy_number is not None:
        candidates.append((easy_number, easy_conf))
    paddle_number, paddle_conf = _read_with_paddle(crop)
    if paddle_number is not None:
        candidates.append((paddle_number, paddle_conf))

    if not candidates:
        return None, 0.0

    best_number, best_conf = max(candidates, key=lambda item: item[1])
    return best_number, round(min(best_conf, 0.99), 3)


def read_jersey_from_detection(frame, cx: int, cy: int, width: int, height: int) -> tuple[int | None, float]:
    x1, y1, x2, y2 = bbox_xyxy_from_center(cx, cy, width, height)
    return read_jersey_from_bbox(frame, x1, y1, x2, y2)


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
        return {"skipped": True, "reason": "no_video"}

    from stats import _resolve_relational_game_id

    relational_game_id = _resolve_relational_game_id(db, game_id)
    analysis_key = str(game_id)
    if relational_game_id is not None:
        scope_sql = "(d.relational_game_id = ? OR (d.relational_game_id IS NULL AND d.game_id = ?))"
        scope_params = (relational_game_id, analysis_key)
    else:
        scope_sql = "d.game_id = ?"
        scope_params = (analysis_key,)

    window_ms = int(ai_settings.get("jersey_ocr_event_window_ms", 3000))
    max_per_cluster = int(ai_settings.get("jersey_ocr_max_samples_per_cluster", 40))
    offsets_ms = ai_settings.get("jersey_ocr_event_offsets_ms")
    if not offsets_ms:
        offsets_ms = [-2000, 0, 2000]

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
            (relational_game_id, analysis_key),
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
            (analysis_key,),
        ).fetchall()

    if not events:
        return {"skipped": True, "reason": "no_events"}

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

    import cv2  # noqa: WPS433

    cap = cv2.VideoCapture(video_path, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        return {"skipped": True, "reason": "video_unreadable"}

    frame_cache: dict[int, object] = {}
    reads = 0
    updated = 0
    try:
        for target in sorted(targets, key=lambda item: item["timestamp_ms"]):
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
        db.commit()
    finally:
        cap.release()

    return {
        "skipped": False,
        "events_sampled": sum(len(v) for v in samples_by_cluster.values()),
        "targets": len(targets),
        "ocr_attempts": reads,
        "updated": updated,
        "clusters": len(samples_by_cluster),
    }
