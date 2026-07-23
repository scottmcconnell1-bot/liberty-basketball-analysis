"""Auto-digitize Fast Scout playbook diagram PNGs into court positions.

Detects offense digits (1-5) and defense labels (x1-x5), maps image pixels
into the playbook SVG half-court viewBox (500 x 470, basket near y=448).

Uses OpenCV connected components + EasyOCR on crops, with template matching
as a backup for sparse offense digits. Does not invent defense markers unless
OCR sees an "x" label; does not invent offense from digits already paired to X.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np

SVG_W = 500.0
SVG_H = 470.0
MIN_CONF = 0.30
MIN_MARKERS_ACCEPT = 3
PAD = 4
BORDER_MARGIN = 8

_READER = None


def _cv2():
    import cv2

    return cv2


def get_easyocr_reader():
    """Lazy singleton EasyOCR reader (CPU)."""
    global _READER
    if _READER is None:
        import easyocr

        _READER = easyocr.Reader(["en"], gpu=False)
    return _READER


@dataclass
class MarkerHit:
    key: str  # o1..o5 / d1..d5
    x: float
    y: float
    conf: float
    source: str = "ocr"
    raw: str = ""

    @property
    def kind(self) -> str:
        return "offense" if self.key.startswith("o") else "defense"

    @property
    def number(self) -> int:
        return int(self.key[1:])


@dataclass
class DigitizeResult:
    positions: dict[str, dict[str, float]] = field(default_factory=dict)
    markers: list[MarkerHit] = field(default_factory=list)
    movements: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    accepted: bool = False
    skip_reason: str = ""
    court_bbox: tuple[int, int, int, int] = (0, 0, 0, 0)
    debug: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "positions": self.positions,
            "movements": self.movements,
            "confidence": round(self.confidence, 3),
            "accepted": self.accepted,
            "skip_reason": self.skip_reason,
            "marker_count": len(self.markers),
            "offense_count": sum(1 for m in self.markers if m.kind == "offense"),
            "defense_count": sum(1 for m in self.markers if m.kind == "defense"),
            "court_bbox": list(self.court_bbox),
            "markers": [
                {
                    "key": m.key,
                    "x": m.x,
                    "y": m.y,
                    "conf": round(m.conf, 3),
                    "source": m.source,
                    "raw": m.raw,
                }
                for m in self.markers
            ],
            "debug": self.debug,
        }


def resolve_image_path(source_image: str, upload_root: str | Path | None = None) -> Path | None:
    """Map a /uploads/... URL to a filesystem path."""
    if not source_image:
        return None
    raw = str(source_image).strip().replace("\\", "/")
    if raw.startswith("/uploads/"):
        rel = raw[len("/uploads/") :]
    elif raw.startswith("uploads/"):
        rel = raw[len("uploads/") :]
    else:
        rel = raw.lstrip("/")
    roots: list[Path] = []
    if upload_root:
        roots.append(Path(upload_root))
    env = os.environ.get("LIBERTY_UPLOAD_FOLDER")
    if env:
        roots.append(Path(env))
    roots.append(Path("uploads"))
    # Also try repo-relative from this file
    roots.append(Path(__file__).resolve().parent / "uploads")
    for root in roots:
        cand = root / rel
        if cand.is_file():
            return cand
    return None


def detect_court_frame(gray: np.ndarray) -> tuple[int, int, int, int]:
    """Find the outer court rectangle. Returns x0,y0,x1,y1 in image coords."""
    cv2 = _cv2()
    h, w = gray.shape[:2]
    img_area = float(h * w)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 40, 120)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    cnts, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    best = None
    best_score = -1.0
    cx_img, cy_img = w / 2.0, h * 0.42

    for c in cnts:
        area = cv2.contourArea(c)
        if area < 0.12 * img_area or area > 0.55 * img_area:
            continue
        x, y, bw, bh = cv2.boundingRect(c)
        if bw < 80 or bh < 80:
            continue
        aspect = bw / float(bh)
        if aspect < 0.75 or aspect > 1.45:
            continue
        # Prefer frames in the upper/mid page (diagram), not notes below
        if y < 60 or y > 0.45 * h:
            continue
        if y + bh > 0.78 * h:
            continue
        ccx, ccy = x + bw / 2.0, y + bh / 2.0
        dist = abs(ccx - cx_img) / w + abs(ccy - cy_img) / h
        if dist > 0.5:
            continue
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        rectness = 1.0 if len(approx) >= 4 else 0.75
        # Prefer roughly square half-court frames
        square = 1.0 - min(0.35, abs(1.0 - aspect))
        score = area * rectness * square * (1.0 - 0.4 * dist)
        if score > best_score:
            best_score = score
            best = (x, y, x + bw, y + bh)

    if best is not None:
        return best

    # Typical Fast Scout 1224x1584 layout (header + square court + notes)
    if w >= 1000 and h >= 1400:
        return (80, 240, 1140, 1020)
    return (
        int(0.065 * w),
        int(0.15 * h),
        int(0.93 * w),
        int(0.64 * h),
    )


def _binarize_ink(roi: np.ndarray) -> np.ndarray:
    cv2 = _cv2()
    blur = cv2.GaussianBlur(roi, (3, 3), 0)
    _, otsu = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    white_frac = float(np.mean(otsu > 0))
    if white_frac > 0.35 or white_frac < 0.005:
        return cv2.adaptiveThreshold(
            blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 8
        )
    return otsu


def _remove_court_lines(ink: np.ndarray) -> np.ndarray:
    cv2 = _cv2()
    h, w = ink.shape[:2]
    hk = max(25, w // 20)
    vk = max(25, h // 20)
    horiz = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (hk, 1)))
    vert = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, vk)))
    cleaned = cv2.subtract(ink, cv2.bitwise_or(horiz, vert))
    cleaned = cv2.morphologyEx(
        cleaned, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    )
    return cleaned


def _solidity(cnt) -> float:
    cv2 = _cv2()
    area = cv2.contourArea(cnt)
    ha = cv2.contourArea(cv2.convexHull(cnt))
    return float(area / ha) if ha > 1e-6 else 0.0


def _find_candidates(ink: np.ndarray, court_w: int, court_h: int) -> list[dict]:
    cv2 = _cv2()
    cnts, _ = cv2.findContours(ink, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cands = []
    for c in cnts:
        area = cv2.contourArea(c)
        if area < 70 or area > 2800:
            continue
        x, y, bw, bh = cv2.boundingRect(c)
        if bh < 16 or bh > 80:
            continue
        aspect = bw / float(bh)
        if aspect < 0.25 or aspect > 2.8:
            continue
        if _solidity(c) < 0.28:
            continue
        if x < BORDER_MARGIN or y < BORDER_MARGIN:
            continue
        if x + bw > court_w - BORDER_MARGIN or y + bh > court_h - BORDER_MARGIN:
            continue
        cands.append(
            {
                "x": x,
                "y": y,
                "w": bw,
                "h": bh,
                "area": area,
                "cx": x + bw / 2.0,
                "cy": y + bh / 2.0,
            }
        )
    return cands


def _crop_pad(img: np.ndarray, c: dict, pad: int = PAD) -> np.ndarray:
    h, w = img.shape[:2]
    x0 = max(0, c["x"] - pad)
    y0 = max(0, c["y"] - pad)
    x1 = min(w, c["x"] + c["w"] + pad)
    y1 = min(h, c["y"] + c["h"] + pad)
    return img[y0:y1, x0:x1]


def px_to_svg(fx: float, fy: float, court: tuple[int, int, int, int]) -> tuple[float, float]:
    """Map full-image coords → SVG. Fast Scout basket is at image TOP → SVG high y."""
    x0, y0, x1, y1 = court
    cw = max(1, x1 - x0)
    ch = max(1, y1 - y0)
    nx = (fx - x0) / cw
    ny = (fy - y0) / ch
    sx = float(np.clip(nx * SVG_W, 8, SVG_W - 8))
    sy = float(np.clip((1.0 - ny) * SVG_H, 8, SVG_H - 8))
    return (round(sx, 1), round(sy, 1))


def _classify_text(text: str) -> tuple[str | None, int | None]:
    t = (text or "").strip()
    compact = re.sub(r"\s+", "", t)
    m = re.match(r"^[xX]([1-5])$", compact)
    if m:
        return ("defense", int(m.group(1)))
    if re.match(r"^[1-5]$", compact):
        return ("offense", int(compact))
    if compact.lower() == "x":
        return ("x_only", None)
    return (None, None)


def _ocr_crop(reader, crop_gray: np.ndarray) -> tuple[str, float]:
    cv2 = _cv2()
    if crop_gray.size == 0:
        return ("", 0.0)
    h, w = crop_gray.shape[:2]
    scale = max(1.0, 48.0 / max(h, 1))
    up = (
        cv2.resize(crop_gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        if scale > 1.05
        else crop_gray
    )
    canvas = cv2.copyMakeBorder(up, 8, 8, 8, 8, cv2.BORDER_CONSTANT, value=255)
    try:
        res = reader.readtext(canvas, allowlist="012345xX", paragraph=False, detail=1)
    except Exception:
        res = reader.readtext(canvas, paragraph=False, detail=1)
    if not res:
        return ("", 0.0)
    best = max(res, key=lambda r: float(r[2]))
    return (str(best[1]).strip(), float(best[2]))


def _render_template(label: str, scale: float) -> np.ndarray:
    from PIL import Image, ImageDraw, ImageFont

    font_size = max(12, int(40 * scale))
    try:
        font = ImageFont.truetype("arialbd.ttf", font_size)
    except Exception:
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()
    tmp = Image.new("L", (1, 1), 255)
    dr = ImageDraw.Draw(tmp)
    bbox = dr.textbbox((0, 0), label, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    img = Image.new("L", (tw + 10, th + 10), 255)
    dr = ImageDraw.Draw(img)
    dr.text((5 - bbox[0], 5 - bbox[1]), label, fill=0, font=font)
    return np.array(img)


def _template_match(
    roi_gray: np.ndarray,
    court_offset: tuple[int, int],
    *,
    want_offense: bool = True,
    want_defense: bool = False,
) -> list[dict]:
    cv2 = _cv2()
    ox, oy = court_offset
    img = roi_gray.copy()
    results: list[dict] = []
    scales = [0.7, 0.85, 1.0, 1.15, 1.3, 1.5]

    def run(labels: list[str], kind: str, thresh: float):
        for lab in labels:
            best_val = -1.0
            best_loc = None
            best_wh = None
            for sc in scales:
                tmpl = _render_template(lab, sc)
                th, tw = tmpl.shape[:2]
                if th >= img.shape[0] or tw >= img.shape[1]:
                    continue
                for t in (tmpl, 255 - tmpl):
                    res = cv2.matchTemplate(img, t, cv2.TM_CCOEFF_NORMED)
                    _mn, max_v, _ml, max_l = cv2.minMaxLoc(res)
                    if max_v > best_val:
                        best_val = float(max_v)
                        best_loc = max_l
                        best_wh = (tw, th)
            if best_loc is not None and best_val >= thresh:
                tw, th = best_wh
                mid = int(re.search(r"[1-5]", lab).group(0))
                results.append(
                    {
                        "kind": kind,
                        "id": mid,
                        "conf": best_val,
                        "fx": ox + best_loc[0] + tw / 2.0,
                        "fy": oy + best_loc[1] + th / 2.0,
                        "raw": lab,
                        "source": "template",
                    }
                )

    if want_offense:
        run([str(n) for n in range(1, 6)], "offense", 0.62)
    if want_defense:
        run([f"x{n}" for n in range(1, 6)] + [f"X{n}" for n in range(1, 6)], "defense", 0.62)
    return results


def _dedupe(markers: list[dict], min_conf: float = MIN_CONF) -> list[dict]:
    best: dict[str, dict] = {}
    for m in markers:
        if m["conf"] < min_conf:
            continue
        key = f"{'o' if m['kind'] == 'offense' else 'd'}{m['id']}"
        if key not in best or m["conf"] > best[key]["conf"]:
            entry = dict(m)
            entry["key"] = key
            best[key] = entry
    return [best[k] for k in sorted(best.keys(), key=lambda k: (k[0], int(k[1:])))]


def _suppress_offense_near_defense(markers: list[dict], dist_px: float = 42.0) -> list[dict]:
    """Drop offense digits that sit on the same glyph as a defense x-pair."""
    defense = [m for m in markers if m["kind"] == "defense"]
    if not defense:
        return markers
    kept = []
    for m in markers:
        if m["kind"] != "offense":
            kept.append(m)
            continue
        too_close = False
        for d in defense:
            if abs(m["fx"] - d["fx"]) <= dist_px and abs(m["fy"] - d["fy"]) <= dist_px:
                too_close = True
                break
            # same jersey number glued to an X
            if m["id"] == d["id"] and abs(m["fx"] - d["fx"]) <= 55 and abs(m["fy"] - d["fy"]) <= 30:
                too_close = True
                break
        if not too_close:
            kept.append(m)
    return kept


def digitize_image(
    image_path: str | Path,
    *,
    reader=None,
    prefer: str = "auto",
    min_markers: int = MIN_MARKERS_ACCEPT,
    min_conf: float = MIN_CONF,
) -> DigitizeResult:
    """Digitize one diagram PNG into playbook positions.

    prefer: 'offense' | 'defense' | 'auto'
      - offense: suppress fabricated defense (templates never invent X)
      - defense: keep defense; drop offense that pairs to X
      - auto: keep both; only invent defense via OCR x-labels (not templates)
    """
    cv2 = _cv2()
    path = Path(image_path)
    result = DigitizeResult()
    if not path.is_file():
        result.skip_reason = f"missing image: {path}"
        return result

    bgr = cv2.imread(str(path))
    if bgr is None:
        result.skip_reason = f"unreadable image: {path}"
        return result

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    court = detect_court_frame(gray)
    result.court_bbox = court
    x0, y0, x1, y1 = court
    roi = gray[y0:y1, x0:x1]
    rh, rw = roi.shape[:2]
    ink = _binarize_ink(roi)
    cleaned = _remove_court_lines(ink)
    cands = _find_candidates(cleaned, rw, rh)
    if len(cands) < 3:
        for c in _find_candidates(ink, rw, rh):
            if not any(abs(c["cx"] - a["cx"]) < 8 and abs(c["cy"] - a["cy"]) < 8 for a in cands):
                cands.append(c)

    if reader is None:
        reader = get_easyocr_reader()

    hits: list[dict] = []
    x_only: list[dict] = []
    digit_cands: list[tuple[dict, dict]] = []  # (cand, hit) for pairing

    for c in cands:
        crop = _crop_pad(roi, c, PAD)
        crop_ocr = 255 - crop if float(np.mean(crop)) < 127 else crop
        text, conf = _ocr_crop(reader, crop_ocr)
        fx = x0 + c["cx"]
        fy = y0 + c["cy"]
        kind, mid = _classify_text(text)
        if kind == "defense" and mid is not None:
            hits.append(
                {
                    "kind": "defense",
                    "id": mid,
                    "conf": conf,
                    "fx": fx,
                    "fy": fy,
                    "raw": text,
                    "source": "ocr",
                }
            )
        elif kind == "offense" and mid is not None:
            hit = {
                "kind": "offense",
                "id": mid,
                "conf": conf,
                "fx": fx,
                "fy": fy,
                "raw": text,
                "source": "ocr",
            }
            hits.append(hit)
            digit_cands.append((c, hit))
        elif kind == "x_only":
            x_only.append(
                {
                    "fx": fx,
                    "fy": fy,
                    "conf": conf,
                    "roi_cx": c["cx"],
                    "roi_cy": c["cy"],
                    "cand": c,
                }
            )

    # Pair lone X with digit to the right → defense; mark digit for removal
    paired_digit_ids: set[int] = set()
    for xo in x_only:
        best = None
        best_dist = 1e9
        for c, hit in digit_cands:
            dx = c["cx"] - xo["roi_cx"]
            dy = abs(c["cy"] - xo["roi_cy"])
            if dx < -5 or dx > 45 or dy > 22:
                continue
            dist = abs(dx) + dy
            if dist < best_dist:
                best_dist = dist
                best = hit
        if best is not None:
            mid = best["id"]
            paired_digit_ids.add(id(best))
            hits.append(
                {
                    "kind": "defense",
                    "id": mid,
                    "conf": min(1.0, 0.5 * (xo["conf"] + best["conf"]) + 0.2),
                    "fx": (xo["fx"] + best["fx"]) / 2.0,
                    "fy": (xo["fy"] + best["fy"]) / 2.0,
                    "raw": f"x+{best['raw']}",
                    "source": "ocr_x_pair",
                }
            )

    # Remove offense hits that were consumed by x-pairs
    hits = [h for h in hits if not (h["kind"] == "offense" and id(h) in paired_digit_ids)]
    # Also drop offense that share identity objects already in list by proximity
    hits = _suppress_offense_near_defense(hits)

    markers = _dedupe(hits, min_conf=min_conf)
    n_off = sum(1 for m in markers if m["kind"] == "offense")
    n_def = sum(1 for m in markers if m["kind"] == "defense")
    has_x_evidence = n_def > 0 or bool(x_only)

    # Template backup for sparse offense digits only
    tmpl_helped = False
    if n_off < 3 and prefer != "defense":
        tmpl = _template_match(roi, (x0, y0), want_offense=True, want_defense=False)
        existing = {m["key"] for m in markers}
        added = []
        for t in tmpl:
            key = f"o{t['id']}"
            if key in existing or t["conf"] < max(min_conf, 0.62):
                continue
            t["key"] = key
            added.append(t)
        if added:
            tmpl_helped = True
            markers = _dedupe(markers + added, min_conf=min_conf)
            markers = _suppress_offense_near_defense(markers)

    # Optional defense templates only when OCR already saw an X
    if prefer == "defense" and n_def < 3 and has_x_evidence:
        tmpl = _template_match(roi, (x0, y0), want_offense=False, want_defense=True)
        existing = {m["key"] for m in markers}
        added = []
        for t in tmpl:
            key = f"d{t['id']}"
            if key in existing or t["conf"] < max(min_conf, 0.65):
                continue
            t["key"] = key
            added.append(t)
        if added:
            tmpl_helped = True
            markers = _dedupe(markers + added, min_conf=min_conf)

    # Preference filters
    if prefer == "offense":
        markers = [m for m in markers if m["kind"] == "offense"]
    elif prefer == "defense":
        # Keep defense; keep offense only if no defense (mixed diagrams ok when prefer auto)
        if any(m["kind"] == "defense" for m in markers):
            markers = [m for m in markers if m["kind"] == "defense"]

    # Auto: if we have strong defense-only signal (many X, few standalone offense), drop offense
    if prefer == "auto":
        n_off = sum(1 for m in markers if m["kind"] == "offense")
        n_def = sum(1 for m in markers if m["kind"] == "defense")
        if n_def >= 3 and n_off > 0 and n_off <= n_def and has_x_evidence:
            # Likely a defense diagram where digits were part of xN
            # Only drop offense if each offense is near a defense
            near = _suppress_offense_near_defense(markers, dist_px=60)
            if sum(1 for m in near if m["kind"] == "offense") == 0:
                markers = near

    n_off = sum(1 for m in markers if m["kind"] == "offense")
    n_def = sum(1 for m in markers if m["kind"] == "defense")
    total = n_off + n_def

    positions: dict[str, dict[str, float]] = {}
    hits_out: list[MarkerHit] = []
    for m in markers:
        sx, sy = px_to_svg(m["fx"], m["fy"], court)
        key = m["key"]
        positions[key] = {"x": sx, "y": sy}
        hits_out.append(
            MarkerHit(
                key=key,
                x=sx,
                y=sy,
                conf=float(m["conf"]),
                source=str(m.get("source", "ocr")),
                raw=str(m.get("raw", "")),
            )
        )

    confs = [m.conf for m in hits_out]
    mean_conf = float(sum(confs) / len(confs)) if confs else 0.0
    result.positions = positions
    result.markers = hits_out
    result.confidence = mean_conf
    result.debug = {
        "candidates": len(cands),
        "offense": n_off,
        "defense": n_def,
        "tmpl_helped": tmpl_helped,
        "prefer": prefer,
        "image": str(path),
    }

    if total < min_markers or mean_conf < min_conf:
        result.accepted = False
        result.skip_reason = (
            f"low confidence or sparse markers "
            f"(count={total}, mean_conf={mean_conf:.2f}, min_markers={min_markers})"
        )
        # Still return positions for review, but mark not accepted
        return result

    result.accepted = True
    return result


def prefer_from_play_category(category: str | None) -> str:
    cat = (category or "").strip().lower()
    if cat in ("defense", "press"):
        return "defense"
    if cat in ("offense", "transition", "out_of_bounds", "special"):
        return "offense"
    return "auto"


def digitize_play_steps(
    db_path: str | Path,
    play_id: int,
    *,
    upload_root: str | Path | None = None,
    write: bool = False,
    force: bool = False,
    min_markers: int = MIN_MARKERS_ACCEPT,
    reader=None,
) -> dict[str, Any]:
    """Digitize all image steps for one play. Optionally write positions_json."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    play = conn.execute("SELECT id, name, category FROM plays WHERE id = ?", (play_id,)).fetchone()
    if not play:
        conn.close()
        return {"ok": False, "error": f"play {play_id} not found"}

    prefer = prefer_from_play_category(play["category"] if "category" in play.keys() else None)
    steps = conn.execute(
        """SELECT id, step_number, label, positions_json, movements_json, notes, source_image
           FROM play_steps WHERE play_id = ? ORDER BY step_number""",
        (play_id,),
    ).fetchall()

    if reader is None:
        # Load once per play batch
        try:
            reader = get_easyocr_reader()
        except Exception as exc:
            conn.close()
            return {"ok": False, "error": f"EasyOCR unavailable: {exc}"}

    step_results = []
    accepted_n = 0
    for row in steps:
        source = row["source_image"] or ""
        existing = {}
        try:
            existing = json.loads(row["positions_json"] or "{}") or {}
        except json.JSONDecodeError:
            existing = {}
        has_existing = any(
            isinstance(v, dict) and "x" in v and "y" in v for v in existing.values()
        )
        if has_existing and not force:
            step_results.append(
                {
                    "step_number": row["step_number"],
                    "skipped": True,
                    "reason": "already has positions (use --force)",
                    "positions": existing,
                }
            )
            continue
        if not source:
            step_results.append(
                {
                    "step_number": row["step_number"],
                    "skipped": True,
                    "reason": "no source_image",
                }
            )
            continue
        img_path = resolve_image_path(source, upload_root=upload_root)
        if not img_path:
            step_results.append(
                {
                    "step_number": row["step_number"],
                    "skipped": True,
                    "reason": f"image not found: {source}",
                }
            )
            continue

        dig = digitize_image(
            img_path,
            reader=reader,
            prefer=prefer,
            min_markers=min_markers,
        )
        entry = {
            "step_number": row["step_number"],
            "source_image": source,
            "image_path": str(img_path),
            **dig.to_dict(),
        }
        if dig.accepted and write:
            conn.execute(
                "UPDATE play_steps SET positions_json = ? WHERE id = ?",
                (json.dumps(dig.positions), row["id"]),
            )
            entry["written"] = True
            accepted_n += 1
        elif dig.accepted:
            accepted_n += 1
            entry["written"] = False
        else:
            entry["written"] = False
        step_results.append(entry)

    if write:
        conn.execute(
            "UPDATE plays SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (play_id,),
        )
        conn.commit()
    conn.close()

    return {
        "ok": True,
        "play_id": play_id,
        "name": play["name"],
        "category": play["category"] if "category" in play.keys() else "",
        "prefer": prefer,
        "accepted_steps": accepted_n,
        "step_count": len(steps),
        "steps": step_results,
    }


def list_image_only_play_ids(db_path: str | Path) -> list[int]:
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        """
        SELECT DISTINCT play_id FROM play_steps
        WHERE source_image IS NOT NULL AND TRIM(source_image) != ''
          AND (positions_json IS NULL OR TRIM(positions_json) IN ('', '{}'))
        ORDER BY play_id
        """
    ).fetchall()
    conn.close()
    return [int(r[0]) for r in rows]
