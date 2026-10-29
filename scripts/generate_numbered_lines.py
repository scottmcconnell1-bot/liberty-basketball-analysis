"""Draw every play line with its number on each square of the master playbook PDF.

Plan: .team/specs/12_numbered_lines_plan.md, Stage 1 deliverable 2.

One square = one PDF page = one step of a play. Each square gets "S1", "S2"...
at the top left, and every line the extractor found is drawn over the page in
its type colour (pass blue, cut green, dribble orange, screen red) with its
number (1, 2, 3... in the computer's guessed order) at the middle of the line.

Pages are kept or skipped by their header text, never by page range:
  --exclude-drills     skip pages whose header line says "Drills" (Scott item 10;
                       the scouting plays only appear in that section)
  --exclude-scouting   extra comma-separated names; a page whose title or header
                       has one of them is skipped (Scott item 9)
Pages with no player digits (section covers, "Building Blocks") are skipped.

Writes <out>/<play key>/S<n>_page_<ppp>_numbered.png and <out>/index.json
(the play groups that build_choreography_from_extractor reads). Outputs belong
outside the repo (Liberty_Play_Catalog); nothing is written to the PDF.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import playbook_vector_extract as vx  # noqa: E402

KIND_RGB = {
    "pass": (0.10, 0.35, 0.95),
    "cut": (0.05, 0.60, 0.15),
    "dribble": (0.95, 0.55, 0.05),
    "screen": (0.90, 0.10, 0.10),
}
HEADER_MAX_Y = 200.0


def header_lines(page) -> list[str]:
    """Text lines above the court, top to bottom (section, 'Plays', play name, category)."""
    words = [w for w in page.get_text("words") or [] if float(w[1]) < HEADER_MAX_Y]
    rows: dict[int, list] = {}
    for w in sorted(words, key=lambda w: (float(w[1]), float(w[0]))):
        rows.setdefault(round(float(w[1]) / 4), []).append(w[4])
    return [" ".join(v) for _, v in sorted(rows.items())]


def keep_page(header: list[str], exclude_drills: bool, scouting: list[str]) -> bool:
    first = header[0] if header else ""
    if exclude_drills and re.search(r"\bDrills\b", first):
        return False
    text = " ".join(header).lower()
    return not any(name.lower() in text for name in scouting)


def play_name(header: list[str]) -> str:
    rest = [h for h in header[1:] if h.strip().lower() != "plays"]
    return rest[0] if rest else (header[0] if header else "")


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")[:40] or "play"


def group_pages(doc, exclude_drills: bool, scouting: list[str]) -> list[dict]:
    """Consecutive kept pages with the same header section + play name = one play."""
    groups: list[dict] = []
    for i in range(doc.page_count):
        page = doc[i]
        header = header_lines(page)
        if not keep_page(header, exclude_drills, scouting):
            continue
        court = vx._detect_court_rect(page)
        positions, _ = vx._extract_digit_positions(page, court, vx._detect_court_landmarks(page, court))
        if not positions:
            continue
        section = header[0] if header else ""
        name = play_name(header)
        if groups and groups[-1]["section"] == section and groups[-1]["title"] == name and groups[-1]["pages"][-1] == i:
            groups[-1]["pages"].append(i + 1)
        else:
            groups.append({"section": section, "title": name, "pages": [i + 1]})
    for g in groups:
        g["key"] = f"p{g['pages'][0]:03d}_{slug(g['title'])}"
    return groups


def draw_square(page, step: dict, square_no: int) -> None:
    court = vx._detect_court_rect(page)
    landmarks = vx._detect_court_landmarks(page, court)
    page.insert_text((court[0] + 6, court[1] + 22), f"S{square_no}", fontsize=20, color=(0.6, 0, 0.6))
    for n, act in enumerate(step["ink"]["actions"], start=1):
        rgb = KIND_RGB.get(act.get("kind"), (0.3, 0.3, 0.3))
        pts = [vx._svg_to_pdf(p, court, landmarks) for p in act.get("points") or []]
        if len(pts) < 2:
            continue
        page.draw_polyline(pts, color=rgb, width=2.2)
        mx, my = pts[len(pts) // 2] if len(pts) > 2 else ((pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2)
        page.draw_circle((mx, my), 9, color=rgb, fill=(1, 1, 1), width=1.8)
        label = str(n)
        page.insert_text((mx - 3.3 * len(label), my + 4), label, fontsize=11, color=rgb)


def main(argv: list[str] | None = None) -> int:
    import fitz

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pdf", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--exclude-drills", action="store_true")
    ap.add_argument("--exclude-scouting", default="", help="comma-separated team names")
    ap.add_argument("--dpi", type=int, default=110)
    args = ap.parse_args(argv)
    scouting = [s.strip() for s in args.exclude_scouting.split(",") if s.strip()]

    doc = fitz.open(args.pdf)
    try:
        groups = group_pages(doc, args.exclude_drills, scouting)
        args.out.mkdir(parents=True, exist_ok=True)
        total_lines = 0
        for g in groups:
            steps = vx.extract_play_pages(args.pdf, g["pages"])
            g["lines_per_square"] = [len(s["ink"]["actions"]) for s in steps]
            total_lines += sum(g["lines_per_square"])
            gdir = args.out / g["key"]
            gdir.mkdir(exist_ok=True)
            for sq, (page_1, step) in enumerate(zip(g["pages"], steps), start=1):
                page = doc[page_1 - 1]
                draw_square(page, step, sq)
                x0, y0, x1, y1 = vx._detect_court_rect(page)
                clip = fitz.Rect(x0 - 30, y0 - 80, x1 + 30, y1 + 30) & page.rect
                page.get_pixmap(dpi=args.dpi, clip=clip).save(gdir / f"S{sq}_page_{page_1:03d}_numbered.png")
        index = {"pdf": str(args.pdf), "plays": groups}
        (args.out / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    finally:
        doc.close()
    squares = sum(len(g["pages"]) for g in groups)
    print(f"{len(groups)} plays, {squares} squares, {total_lines} numbered lines -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
