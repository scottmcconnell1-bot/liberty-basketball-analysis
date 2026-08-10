"""Digit OCR for cropped cells — EasyOCR → Tesseract → none."""

from __future__ import annotations

import re
from typing import Any

_EASYOCR = None
_EASYOCR_TRIED = False


def ocr_backend_name() -> str:
    if _get_easyocr() is not None:
        return "easyocr"
    if _tesseract_available():
        return "tesseract"
    return "none"


def _get_easyocr():
    global _EASYOCR, _EASYOCR_TRIED
    if _EASYOCR_TRIED:
        return _EASYOCR
    _EASYOCR_TRIED = True
    try:
        import easyocr  # noqa: WPS433

        _EASYOCR = easyocr.Reader(["en"], gpu=False, verbose=False)
    except Exception:
        _EASYOCR = None
    return _EASYOCR


def _tesseract_available() -> bool:
    try:
        import pytesseract  # noqa: WPS433

        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _parse_digits(text: str) -> int | None:
    if not text:
        return None
    cleaned = re.sub(r"[^\d]", "", text)
    if not cleaned:
        return None
    if len(cleaned) > 3:
        cleaned = cleaned[:3]
    try:
        return int(cleaned)
    except ValueError:
        return None


def read_digit_cell(crop_bgr) -> tuple[int | None, float, str]:
    if crop_bgr is None or getattr(crop_bgr, "size", 0) == 0:
        return None, 0.0, "none"

    reader = _get_easyocr()
    if reader is not None:
        try:
            results = reader.readtext(crop_bgr, detail=1, paragraph=False, allowlist="0123456789")
            best_val, best_conf = None, 0.0
            for _bbox, text, conf in results or []:
                parsed = _parse_digits(str(text))
                if parsed is None:
                    continue
                score = float(conf or 0.0)
                if score >= best_conf:
                    best_val, best_conf = parsed, score
            if best_val is not None:
                return best_val, best_conf, "easyocr"
        except Exception:
            pass

    if _tesseract_available():
        try:
            import pytesseract  # noqa: WPS433
            from PIL import Image  # noqa: WPS433
            import numpy as np  # noqa: WPS433

            rgb = crop_bgr[:, :, ::-1] if len(crop_bgr.shape) == 3 else crop_bgr
            text = pytesseract.image_to_string(
                Image.fromarray(np.asarray(rgb)),
                config="--psm 10 -c tessedit_char_whitelist=0123456789",
            )
            parsed = _parse_digits(text)
            if parsed is not None:
                return parsed, 0.5, "tesseract"
        except Exception:
            pass

    return None, 0.0, "none"


def describe_ocr_status() -> dict[str, Any]:
    return {
        "backend": ocr_backend_name(),
        "easyocr": _get_easyocr() is not None,
        "tesseract": _tesseract_available(),
    }
