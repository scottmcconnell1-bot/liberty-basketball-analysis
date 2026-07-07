"""Jersey number OCR from person bounding boxes."""

from __future__ import annotations

import re

_OCR_ENGINE = None
_OCR_UNAVAILABLE = False


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


def _parse_jersey_text(text: str) -> tuple[int | None, float]:
    if not text:
        return None, 0.0
    digits = re.findall(r"\d{1,2}", text)
    if not digits:
        return None, 0.0
    # Prefer two-digit then one-digit in valid jersey range
    candidates = []
    for token in digits:
        value = int(token)
        if 0 <= value <= 99:
            candidates.append(value)
    if not candidates:
        return None, 0.0
    # Single clear number is best
    best = candidates[0]
    confidence = 0.65 if len(candidates) == 1 else 0.45
    return best, confidence


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
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def read_jersey_from_bbox(frame, x1: int, y1: int, x2: int, y2: int) -> tuple[int | None, float]:
    """Return (jersey_number, confidence) from a person bounding box."""
    crop = crop_torso(frame, x1, y1, x2, y2)
    if crop is None:
        return None, 0.0

    reader = _get_ocr_engine()
    if reader is None:
        return None, 0.0

    try:
        results = reader.readtext(crop, detail=1, paragraph=False, allowlist="0123456789")
    except Exception:
        return None, 0.0

    best_number = None
    best_conf = 0.0
    for _bbox, text, conf in results:
        number, parsed_conf = _parse_jersey_text(str(text))
        if number is None:
            continue
        combined = float(conf) * parsed_conf
        if combined > best_conf:
            best_conf = combined
            best_number = number

    if best_number is None:
        return None, 0.0
    return best_number, round(min(best_conf, 0.99), 3)
