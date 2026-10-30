"""Grade the extractor against the PDF itself: end marks that end on a kept line.

Plan: .team/specs/12_numbered_lines_plan_v4.md, "Grading - Completeness Against
the PDF Itself". FastDraw ends every play stroke with a small filled arrowhead or
screen bar (playbook_vector_extract._end_marks). Per play page:

  marks      arrowheads + screen bars on the page
  kept       marks whose stroke was kept as a line (its start snapped to a digit)
  dropped    marks attached to a stroke that was then dropped (no start digit)
  unattached marks no stroke picked up

Grade = kept / marks over all play pages; pass bar 90%.

Also writes the chained-lines distance report (plan Gap 1, "Radius validation"):
for every dropped marked stroke, the distance in PDF points from its start to the
nearest kept line's end (a dribble squiggle counts) on the same page. No radius is
chosen here; Scott sees the list first.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import playbook_vector_extract as vx  # noqa: E402

PASS_BAR = 0.90


def grade_page(pdf: Path, page_1: int) -> dict:
    import fitz

    with fitz.open(pdf) as doc:
        heads, bars = vx._end_marks(doc[page_1 - 1].get_drawings() or [])
    trace: list[dict] = []
    vx.extract_page(pdf, page_1, trace=trace)
    kept = [r for r in trace if r["kept"]]  # includes dribble squiggles (no mark)
    marked_kept = [r for r in kept if r["mark"] is not None]
    dropped = [r for r in trace if not r["kept"]]
    chains = []
    for r in dropped:
        near = min(kept, key=lambda k: math.dist(r["start"], k["end"]), default=None)
        chains.append(
            {
                "page": page_1,
                "start": [round(v, 1) for v in r["start"]],
                "mark": r["mark"][0],
                "nearest_end_pid": near["pid"] if near else None,
                "dist_pt": round(math.dist(r["start"], near["end"]), 1) if near else None,
            }
        )
    marks = len(heads) + len(bars)
    return {
        "page": page_1,
        "marks": marks,
        "kept": len(marked_kept),
        "dropped": len(dropped),
        "unattached": marks - len(marked_kept) - len(dropped),
        "chains": chains,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pdf", required=True, type=Path)
    ap.add_argument("--numbered-dir", required=True, type=Path, help="folder with index.json")
    ap.add_argument("--out", required=True, type=Path, help="completeness_report.md")
    args = ap.parse_args(argv)

    index = json.loads((args.numbered_dir / "index.json").read_text(encoding="utf-8"))
    rows = []
    for play in index["plays"]:
        for page_1 in play["pages"]:
            row = grade_page(args.pdf, page_1)
            row["play"] = play["key"]
            rows.append(row)

    marks = sum(r["marks"] for r in rows)
    kept = sum(r["kept"] for r in rows)
    dropped = sum(r["dropped"] for r in rows)
    unattached = sum(r["unattached"] for r in rows)
    grade = kept / marks if marks else 0.0
    chains = sorted((c for r in rows for c in r["chains"]), key=lambda c: (c["dist_pt"] is None, c["dist_pt"] or 0))

    out = [
        "# Completeness grade - end marks on kept lines",
        "",
        f"PDF: {args.pdf}",
        f"Play pages: {len(rows)} (from {args.numbered_dir / 'index.json'})",
        "",
        f"End marks: {marks}  |  on a kept line: {kept}  |  on a dropped stroke: {dropped}  |  not picked up: {unattached}",
        f"**Grade: {kept}/{marks} = {grade:.1%}  (pass bar {PASS_BAR:.0%}: {'PASS' if grade >= PASS_BAR else 'FAIL'})**",
        "",
        "## Per page",
        "",
        "| Page | Play | Marks | Kept | Dropped | Not picked up | % |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        pct = f"{r['kept'] / r['marks']:.0%}" if r["marks"] else "-"
        out.append(f"| {r['page']} | {r['play']} | {r['marks']} | {r['kept']} | {r['dropped']} | {r['unattached']} | {pct} |")
    out += [
        "",
        "## Chained-lines distance report (no radius chosen)",
        "",
        "Every dropped marked stroke: distance in PDF points from its start to the nearest",
        "kept line's end on the same page (dribble squiggles count), and whose line that is.",
        "Sorted by distance. Pictures: Liberty_Play_Catalog/chain_check/index.html.",
        "",
        "| Page | Start (PDF pt) | Mark | Nearest kept end | Distance (pt) |",
        "|---|---|---|---|---|",
    ]
    for c in chains:
        out.append(f"| {c['page']} | {c['start']} | {c['mark']} | {c['nearest_end_pid'] or '-'} | {c['dist_pt'] if c['dist_pt'] is not None else 'no kept line'} |")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(out) + "\n", encoding="utf-8")
    (args.out.with_suffix(".json")).write_text(json.dumps({"grade": grade, "rows": rows}, indent=1), encoding="utf-8")
    print(f"pages {len(rows)}  marks {marks}  kept {kept}  dropped {dropped}  not picked up {unattached}  grade {grade:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
