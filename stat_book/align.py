"""Perspective align helpers (OpenCV when available)."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence


def _cv2_np():
    try:
        import cv2  # noqa: WPS433
        import numpy as np  # noqa: WPS433

        return cv2, np
    except Exception:
        return None, None


def load_image_bgr(path: str | Path):
    cv2, np = _cv2_np()
    if cv2 is not None:
        return cv2.imread(str(path))
    try:
        from PIL import Image  # noqa: WPS433
        import numpy as np  # noqa: WPS433

        img = Image.open(path).convert("RGB")
        return np.array(img)[:, :, ::-1].copy()
    except Exception:
        return None


def save_image_bgr(path: str | Path, image) -> bool:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2, _ = _cv2_np()
    if cv2 is not None:
        return bool(cv2.imwrite(str(path), image))
    try:
        from PIL import Image  # noqa: WPS433
        import numpy as np  # noqa: WPS433

        rgb = image[:, :, ::-1] if getattr(image, "ndim", 0) == 3 else image
        Image.fromarray(np.asarray(rgb)).save(str(path))
        return True
    except Exception:
        return False


def warp_to_template(image, corners: Sequence[Sequence[float]], out_width: int, out_height: int):
    cv2, np = _cv2_np()
    if cv2 is None or image is None or len(corners) != 4:
        return None
    try:
        src = np.array([[float(x), float(y)] for x, y in corners], dtype=np.float32)
        dst = np.array(
            [[0, 0], [out_width - 1, 0], [out_width - 1, out_height - 1], [0, out_height - 1]],
            dtype=np.float32,
        )
        matrix = cv2.getPerspectiveTransform(src, dst)
        return cv2.warpPerspective(image, matrix, (out_width, out_height))
    except Exception:
        return None


def crop_norm_cell(image, x0: float, y0: float, x1: float, y1: float, pad: float = 0.0):
    if image is None:
        return None
    h, w = image.shape[:2]
    x0 = max(0.0, min(1.0, x0 - pad))
    x1 = max(0.0, min(1.0, x1 + pad))
    y0 = max(0.0, min(1.0, y0 - pad))
    y1 = max(0.0, min(1.0, y1 + pad))
    xa, xb = int(x0 * w), int(x1 * w)
    ya, yb = int(y0 * h), int(y1 * h)
    if xb <= xa or yb <= ya:
        return None
    return image[ya:yb, xa:xb].copy()
