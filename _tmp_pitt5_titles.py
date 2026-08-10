"""Read page titles; analyze ink on 172/173."""
from pathlib import Path

import cv2

from playbook_sheet_align import (
    analyze_sheet_image,
    find_court_bbox,
    trace_marked_paths_for_transition,
)

base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")
out = Path("_tmp_pitt5_vis")
out.mkdir(exist_ok=True)

for pg in range(168, 177):
    p = base / f"page_{pg:04d}.png"
    if not p.is_file():
        continue
    img = cv2.imread(str(p))
    if img is None:
        continue
    h, w = img.shape[:2]
    band = img[0 : int(h * 0.18), :]
    cv2.imwrite(str(out / f"title_{pg:04d}.png"), band)

for pg in (172, 173):
    p = base / f"page_{pg:04d}.png"
    align = analyze_sheet_image(p)
    pos = align["positions"]
    print(f"\n=== PAGE {pg} OCR ===")
    print({k: (round(v["x"], 1), round(v["y"], 1)) for k, v in pos.items()})
    marked = trace_marked_paths_for_transition(p, pos, pos)
    print("marks", marked.get("marks"))
    for k, v in (marked.get("paths") or {}).items():
        print(
            f"  path {k}: n={len(v)} "
            f"start=({v[0]['x']:.1f},{v[0]['y']:.1f}) "
            f"end=({v[-1]['x']:.1f},{v[-1]['y']:.1f})"
        )
    print(
        "passes",
        [
            (pp.get("fromPid"), pp.get("toPid"), pp.get("orphan"))
            for pp in marked.get("passes") or []
        ],
    )

    img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
    bbox = find_court_bbox(img)
    x0, y0, x1, y1 = bbox
    crop = img[y0:y1, x0:x1]
    vis = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
    h, w = crop.shape[:2]

    def to_px(pt):
        return int(pt["x"] / 500.0 * w), int(pt["y"] / 470.0 * h)

    for oid, ptd in pos.items():
        x, y = to_px(ptd)
        cv2.circle(vis, (x, y), 8, (0, 255, 0), 2)
        cv2.putText(vis, oid, (x + 10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 0), 2)

    colors = {
        "o4": (255, 0, 0),
        "o5": (0, 0, 255),
        "o4_drop": (255, 0, 255),
        "o1": (0, 255, 255),
        "o2": (255, 255, 0),
        "o3": (180, 180, 180),
    }
    for oid, poly in (marked.get("paths") or {}).items():
        col = colors.get(oid, (200, 200, 200))
        pts = [to_px(pt) for pt in poly]
        for a, b in zip(pts, pts[1:]):
            cv2.line(vis, a, b, col, 2)
        if pts:
            cv2.circle(vis, pts[-1], 6, col, -1)
            cv2.putText(
                vis,
                oid + "_end",
                (pts[-1][0] + 4, pts[-1][1] - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                col,
                1,
            )
    cv2.imwrite(str(out / f"page{pg}_paths.png"), vis)
    print("wrote", out / f"page{pg}_paths.png")
