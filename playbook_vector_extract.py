"""Extract structured play data from FastDraw vector PDFs (no OCR).

Liberty's scout PDFs (creator=FastDraw) are native vector: digit glyphs as text
and cut/pass/dribble strokes as draw paths — zero embedded page images. This
module reads those operators directly and emits the same choreography shape the
sticky review UI already edits:

  positions o1..o5, court_frac, ink.paths / marks / passes

OCR remains a fallback for raster sheets or when the sibling PDF is missing.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

COURT_W = 500.0
COURT_H = 470.0

# FastDraw court outline on letter pages (measured across 1-Game / Rip / Pitt 5).
_DEFAULT_COURT_PDF = (44.0, 163.4, 569.0, 618.4)

_PAGE_RE = re.compile(r"page_(\d+)\.(?:png|jpe?g)$", re.I)


def classify_pdf(pdf_path: str | Path) -> dict[str, Any]:
    """Return Proven vector/raster stats for a PDF."""
    import fitz

    path = Path(pdf_path)
    doc = fitz.open(path)
    try:
        pages = doc.page_count
        pages_with_text = 0
        pages_with_drawings = 0
        pages_mostly_img = 0
        total_text = 0
        total_drawings = 0
        total_images = 0
        for i in range(pages):
            page = doc[i]
            text = page.get_text() or ""
            drawings = page.get_drawings()
            imgs = page.get_images(full=True)
            total_text += len(text)
            total_drawings += len(drawings)
            total_images += len(imgs)
            if len(text.strip()) > 40:
                pages_with_text += 1
            if len(drawings) > 5:
                pages_with_drawings += 1
            page_area = abs(page.rect.width * page.rect.height) or 1.0
            img_area = 0.0
            for img in imgs:
                try:
                    bbox = page.get_image_bbox(img)
                    img_area += abs(bbox.width * bbox.height)
                except Exception:
                    pass
            if img_area / page_area >= 0.5 and len(text.strip()) < 40 and len(drawings) <= 5:
                pages_mostly_img += 1
        meta = doc.metadata or {}
        if pages_mostly_img > pages * 0.5:
            kind = "raster"
        elif pages_with_drawings > pages * 0.5 or pages_with_text > pages * 0.5:
            kind = "vector"
        else:
            kind = "mixed"
        return {
            "path": str(path),
            "kind": kind,
            "pages": pages,
            "creator": meta.get("creator") or "",
            "producer": meta.get("producer") or "",
            "title": meta.get("title") or "",
            "pages_with_text": pages_with_text,
            "pages_with_drawings": pages_with_drawings,
            "pages_mostly_img": pages_mostly_img,
            "total_text_chars": total_text,
            "total_drawings": total_drawings,
            "total_image_xrefs": total_images,
        }
    finally:
        doc.close()


def resolve_pdf_page_from_sheet(
    image_url_or_path: str | Path,
    *,
    app_root: str | Path | None = None,
) -> tuple[Path, int] | None:
    """Map ``.../bulk_imports/<id>/page_0032.png`` → (``<id>.pdf``, 32)."""
    raw = str(image_url_or_path or "").replace("\\", "/")
    m = _PAGE_RE.search(raw)
    if not m:
        return None
    page_1 = int(m.group(1))
    png = Path(raw)
    if not png.is_absolute():
        root = Path(app_root) if app_root else Path.cwd()
        cleaned = raw.lstrip("/")
        if cleaned.startswith("uploads/"):
            png = root / cleaned
        elif "/uploads/" in raw:
            png = root / raw[raw.index("uploads/") :]
        else:
            png = root / cleaned
    pdf = png.parent if png.suffix.lower() == ".pdf" else png.parent.with_suffix(".pdf")
    # When path is .../hash/page_X.png, sibling PDF is .../hash.pdf
    if png.parent.name and png.parent.parent.name == "bulk_imports":
        pdf = png.parent.with_suffix(".pdf")
        if not pdf.is_file():
            pdf = png.parent.parent / f"{png.parent.name}.pdf"
    if not pdf.is_file():
        # play_imports: page render next to original pdf name is uncommon; bail.
        return None
    return pdf, page_1


def extract_sheet_from_image_url(
    image_url: str,
    *,
    app_root: str | Path | None = None,
    next_positions: dict[str, dict] | None = None,
) -> dict[str, Any] | None:
    """Extract structured step data for a sheet PNG if its vector PDF exists."""
    resolved = resolve_pdf_page_from_sheet(image_url, app_root=app_root)
    if not resolved:
        return None
    pdf_path, page_1 = resolved
    return extract_page(pdf_path, page_1, next_positions=next_positions)


def extract_page(
    pdf_path: str | Path,
    page_1based: int,
    *,
    next_positions: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Extract one FastDraw page into choreography step fields."""
    import fitz

    doc = fitz.open(pdf_path)
    try:
        if page_1based < 1 or page_1based > doc.page_count:
            raise ValueError(f"page {page_1based} out of range (1..{doc.page_count})")
        page = doc[page_1based - 1]
        court = _detect_court_rect(page)
        positions = _extract_digit_positions(page, court)
        ink = _extract_ink(page, court, positions, next_positions=next_positions)
        page_w = float(page.rect.width) or 1.0
        page_h = float(page.rect.height) or 1.0
        x0, y0, x1, y1 = court
        court_frac = {
            "x": round(x0 / page_w, 4),
            "y": round(y0 / page_h, 4),
            "w": round((x1 - x0) / page_w, 4),
            "h": round((y1 - y0) / page_h, 4),
        }
        title = _page_title(page)
        return {
            "ok": True,
            "source": "vector",
            "pdf": str(pdf_path),
            "page": page_1based,
            "title": title,
            "court_frac": court_frac,
            "positions": positions,
            "ink": ink,
        }
    finally:
        doc.close()


def extract_play_pages(
    pdf_path: str | Path,
    page_numbers: list[int],
) -> list[dict[str, Any]]:
    """Extract a sequence of pages; ink uses next-page digit tips when present."""
    steps: list[dict[str, Any]] = []
    parsed: list[dict[str, Any]] = []
    for page_1 in page_numbers:
        parsed.append(extract_page(pdf_path, page_1))
    for i, step in enumerate(parsed):
        nxt = parsed[i + 1]["positions"] if i + 1 < len(parsed) else None
        if nxt:
            # Re-run ink with next tips for better attribution.
            step = extract_page(pdf_path, step["page"], next_positions=nxt)
        steps.append(step)
    return steps


def _page_title(page) -> str:
    words = page.get_text("words") or []
    # Prefer mid-header play name (y ~120-150 on FastDraw letter pages).
    cands = []
    for w in words:
        text = (w[4] or "").strip()
        if not text or text in list("12345"):
            continue
        y0 = float(w[1])
        if 110 <= y0 <= 160 and not text.lower().startswith("offense") and text.lower() not in (
            "plays",
            "zone",
            "man",
            "transition",
            "defense",
        ):
            cands.append(text)
    return " ".join(cands[:4]).strip(" -")


def _detect_court_rect(page) -> tuple[float, float, float, float]:
    """Largest near-white filled rect on the page ≈ half-court diagram."""
    best = None
    best_area = 0.0
    for d in page.get_drawings() or []:
        fill = d.get("fill")
        if not fill or len(fill) < 3:
            continue
        if min(fill[0], fill[1], fill[2]) < 0.95:
            continue
        rect = d.get("rect")
        if rect is None:
            continue
        area = abs(float(rect.width) * float(rect.height))
        if area > best_area:
            best_area = area
            best = (
                float(rect.x0),
                float(rect.y0),
                float(rect.x1),
                float(rect.y1),
            )
    if best and best_area > 50_000:
        return best
    return _DEFAULT_COURT_PDF


def _pdf_to_svg(x: float, y: float, court: tuple[float, float, float, float]) -> dict[str, float]:
    x0, y0, x1, y1 = court
    bw = max(x1 - x0, 1e-6)
    bh = max(y1 - y0, 1e-6)
    return {
        "x": round((float(x) - x0) / bw * COURT_W, 2),
        "y": round((float(y) - y0) / bh * COURT_H, 2),
    }


def _extract_digit_positions(page, court: tuple[float, float, float, float]) -> dict[str, dict[str, float]]:
    x0, y0, x1, y1 = court
    pad = 8.0
    by_digit: dict[int, tuple[float, float, float]] = {}
    for w in page.get_text("words") or []:
        text = (w[4] or "").strip()
        if text not in ("1", "2", "3", "4", "5"):
            continue
        digit = int(text)
        cx = (float(w[0]) + float(w[2])) / 2.0
        cy = (float(w[1]) + float(w[3])) / 2.0
        if cx < x0 - pad or cx > x1 + pad or cy < y0 - pad or cy > y1 + pad:
            continue
        # Prefer the glyph inside the court (ignore footer duplicates).
        area = abs(float(w[2]) - float(w[0])) * abs(float(w[3]) - float(w[1]))
        prev = by_digit.get(digit)
        if prev is None or area >= prev[0]:
            by_digit[digit] = (area, cx, cy)
    out: dict[str, dict[str, float]] = {}
    for digit, (_area, cx, cy) in by_digit.items():
        out[f"o{digit}"] = _pdf_to_svg(cx, cy, court)
    return out


def _poly_from_drawing(d: dict) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for it in d.get("items") or []:
        op = it[0]
        if op == "l":
            p1, p2 = it[1], it[2]
            if not pts:
                pts.append((float(p1.x), float(p1.y)))
            pts.append((float(p2.x), float(p2.y)))
        elif op == "c":
            p1, c1, c2, p2 = it[1], it[2], it[3], it[4]
            if not pts:
                pts.append((float(p1.x), float(p1.y)))
            for t in (0.25, 0.5, 0.75, 1.0):
                u = 1.0 - t
                x = (
                    u**3 * float(p1.x)
                    + 3 * u**2 * t * float(c1.x)
                    + 3 * u * t**2 * float(c2.x)
                    + t**3 * float(p2.x)
                )
                y = (
                    u**3 * float(p1.y)
                    + 3 * u**2 * t * float(c1.y)
                    + 3 * u * t**2 * float(c2.y)
                    + t**3 * float(p2.y)
                )
                pts.append((x, y))
        elif op == "re":
            r = it[1]
            pts.extend(
                [
                    (float(r.x0), float(r.y0)),
                    (float(r.x1), float(r.y0)),
                    (float(r.x1), float(r.y1)),
                    (float(r.x0), float(r.y1)),
                ]
            )
    return pts


def _path_len(pts: list[tuple[float, float]]) -> float:
    total = 0.0
    for a, b in zip(pts, pts[1:]):
        total += ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
    return total


def _simplify(pts: list[tuple[float, float]], min_dist: float = 4.0) -> list[tuple[float, float]]:
    if len(pts) <= 2:
        return pts
    out = [pts[0]]
    for p in pts[1:]:
        q = out[-1]
        if ((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) ** 0.5 >= min_dist:
            out.append(p)
    if out[-1] != pts[-1]:
        out.append(pts[-1])
    return out


def _is_court_geometry(pts: list[tuple[float, float]], court: tuple[float, float, float, float], width: float | None) -> bool:
    """Filter FastDraw court lines (thin dashed arcs / key / baseline)."""
    if not pts:
        return True
    x0, y0, x1, y1 = court
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    # Mirror court below the page (FastDraw sometimes emits a reflected copy).
    if min(ys) > y1 + 20:
        return True
    # Outer white court fill already excluded; thin width ~1.46 = court ink.
    if width is not None and width < 2.2:
        # Exception: keep nothing thin — play ink is thicker (~2.92).
        return True
    # Huge closed loops spanning most of the court = 3pt / court outline.
    bw = max(xs) - min(xs)
    bh = max(ys) - min(ys)
    if bw > (x1 - x0) * 0.55 and bh > (y1 - y0) * 0.25 and len(pts) <= 20:
        return True
    return False


def _nearest_oid(
    pt: tuple[float, float],
    positions_pdf: dict[str, tuple[float, float]],
    *,
    max_dist: float = 55.0,
) -> str | None:
    best = None
    best_d = max_dist
    for oid, (x, y) in positions_pdf.items():
        d = ((pt[0] - x) ** 2 + (pt[1] - y) ** 2) ** 0.5
        if d < best_d:
            best_d = d
            best = oid
    return best


def _extract_ink(
    page,
    court: tuple[float, float, float, float],
    positions: dict[str, dict[str, float]],
    *,
    next_positions: dict[str, dict] | None = None,
) -> dict[str, Any]:
    x0, y0, x1, y1 = court
    # Positions back to PDF for attribution.
    positions_pdf: dict[str, tuple[float, float]] = {}
    bw = max(x1 - x0, 1e-6)
    bh = max(y1 - y0, 1e-6)
    for oid, pos in positions.items():
        positions_pdf[oid] = (
            x0 + float(pos["x"]) / COURT_W * bw,
            y0 + float(pos["y"]) / COURT_H * bh,
        )

    paths: dict[str, list[dict[str, float]]] = {}
    marks: dict[str, Any] = {}
    passes: list[dict[str, Any]] = []

    for d in page.get_drawings() or []:
        fill = d.get("fill")
        color = d.get("color")
        width = d.get("width")
        pts = _poly_from_drawing(d)
        if len(pts) < 2:
            continue
        L = _path_len(pts)
        if L < 35:
            continue

        # Dribble squiggles: long filled black multi-segment paths.
        if fill and color is None and len(d.get("items") or []) >= 20 and L > 150:
            pts_s = _simplify(pts, min_dist=6.0)
            if _is_court_geometry(pts_s, court, width=3.0):
                continue
            start = pts_s[0]
            oid = _nearest_oid(start, positions_pdf, max_dist=70.0)
            if not oid:
                continue
            svg = [_pdf_to_svg(x, y, court) for x, y in pts_s]
            # Snap start to digit.
            svg[0] = {"x": float(positions[oid]["x"]), "y": float(positions[oid]["y"])}
            paths[oid] = svg
            marks[oid] = "dribble"
            continue

        # Play strokes: thicker dashed black lines (cuts / passes / screens).
        if color is None or fill:
            continue
        if width is None or width < 2.2:
            continue
        if _is_court_geometry(pts, court, width):
            continue
        # Skip small ball / player circle outlines (nearly closed, short loop).
        if L < 130 and abs(pts[0][0] - pts[-1][0]) < 8 and abs(pts[0][1] - pts[-1][1]) < 8:
            continue

        pts_s = _simplify(pts, min_dist=3.5)
        start, end = pts_s[0], pts_s[-1]
        # Orient start toward a digit when possible.
        start_oid = _nearest_oid(start, positions_pdf, max_dist=60.0)
        end_oid = _nearest_oid(end, positions_pdf, max_dist=60.0)
        if start_oid is None and end_oid is not None:
            pts_s = list(reversed(pts_s))
            start, end = pts_s[0], pts_s[-1]
            start_oid, end_oid = end_oid, _nearest_oid(end, positions_pdf, max_dist=60.0)
        if start_oid is None:
            continue

        svg = [_pdf_to_svg(x, y, court) for x, y in pts_s]
        svg[0] = {"x": float(positions[start_oid]["x"]), "y": float(positions[start_oid]["y"])}

        # Pass heuristic: endpoint near a *different* digit (or next-page tip).
        tip_oid = end_oid
        if tip_oid is None and next_positions:
            # Map next SVG tips into this page PDF space for proximity.
            tip_oid = _nearest_next(end, next_positions, court)

        kind = "cut"
        if tip_oid and tip_oid != start_oid:
            kind = "pass"
            passes.append(
                {
                    "fromPid": start_oid,
                    "toPid": tip_oid,
                    "type": "pass",
                    "points": svg,
                }
            )
            # Still keep a path for the passer so Play All can animate.
            if start_oid not in paths:
                paths[start_oid] = svg
                marks[start_oid] = "pass"
            continue

        # Prefer longer path if multiple strokes attribute to same player.
        prev = paths.get(start_oid)
        if prev is None or _path_len([(p["x"], p["y"]) for p in svg]) > _path_len(
            [(p["x"], p["y"]) for p in prev]
        ):
            paths[start_oid] = svg
            marks[start_oid] = kind

    return {"paths": paths, "marks": marks, "passes": passes}


def _nearest_next(
    pdf_pt: tuple[float, float],
    next_positions: dict[str, dict],
    court: tuple[float, float, float, float],
) -> str | None:
    x0, y0, x1, y1 = court
    bw = max(x1 - x0, 1e-6)
    bh = max(y1 - y0, 1e-6)
    best = None
    best_d = 70.0
    for oid, pos in (next_positions or {}).items():
        if not isinstance(pos, dict) or "x" not in pos or "y" not in pos:
            continue
        px = x0 + float(pos["x"]) / COURT_W * bw
        py = y0 + float(pos["y"]) / COURT_H * bh
        d = ((pdf_pt[0] - px) ** 2 + (pdf_pt[1] - py) ** 2) ** 0.5
        if d < best_d:
            best_d = d
            best = str(oid)
    return best
