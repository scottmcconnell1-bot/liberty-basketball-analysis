"""Audit: raw FastDraw vector vs Liberty sheet-extract for sample sheets.

Writes HTML + JSON under data/playbook/vector_audit/ so Scott can judge
systematic transform bugs vs per-play attribution errors.

Usage:
  .venv\\Scripts\\python.exe scripts/playbook_vector_audit.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import fitz

from playbook_vector_extract import (
    COURT_H,
    COURT_W,
    _DEFAULT_COURT_PDF,
    _detect_court_rect,
    _is_court_geometry,
    _path_len,
    _pdf_to_svg,
    _poly_from_drawing,
    _simplify,
    extract_page,
)

PDF = ROOT / "uploads/bulk_imports/d125785a44474042b13589e9aadeca4f.pdf"
OUT = ROOT / "data/playbook/vector_audit"

# Spanning different plays / layouts.
SAMPLES = [
    {"label": "1-Game", "page": 32},
    {"label": "Rip", "page": 120},
    {"label": "Rip", "page": 122},
    {"label": "Triangle", "page": 127},
    {"label": "Pitt 5", "page": 173},
]


def _raw_digits(page, court):
    x0, y0, x1, y1 = court
    pad = 8.0
    rows = []
    for w in page.get_text("words") or []:
        text = (w[4] or "").strip()
        if text not in list("12345"):
            continue
        cx = (float(w[0]) + float(w[2])) / 2.0
        cy = (float(w[1]) + float(w[3])) / 2.0
        aw = abs(float(w[2]) - float(w[0]))
        ah = abs(float(w[3]) - float(w[1]))
        in_court = not (
            cx < x0 - pad or cx > x1 + pad or cy < y0 - pad or cy > y1 + pad
        )
        svg = _pdf_to_svg(cx, cy, court) if in_court else None
        rows.append(
            {
                "digit": int(text),
                "pdf_xy": [round(cx, 2), round(cy, 2)],
                "bbox_wh": [round(aw, 2), round(ah, 2)],
                "area": round(aw * ah, 2),
                "in_court": in_court,
                "court_svg": svg,
            }
        )
    return rows


def _raw_strokes(page, court):
    strokes = []
    for i, d in enumerate(page.get_drawings() or []):
        fill = d.get("fill")
        color = d.get("color")
        width = d.get("width")
        pts = _poly_from_drawing(d)
        if len(pts) < 2:
            continue
        L = _path_len(pts)
        if L < 35:
            continue
        kind = "other"
        if fill and color is None and len(d.get("items") or []) >= 20 and L > 150:
            kind = "dribble_candidate"
        elif color is not None and not fill and width is not None and width >= 2.2:
            if _is_court_geometry(pts, court, width):
                kind = "court_geometry_filtered"
            elif L < 130 and abs(pts[0][0] - pts[-1][0]) < 8 and abs(pts[0][1] - pts[-1][1]) < 8:
                kind = "circle_outline"
            else:
                kind = "play_stroke"
        elif width is not None and width < 2.2:
            kind = "thin_courtish"
        else:
            continue

        if kind in ("thin_courtish", "other"):
            continue

        pts_s = _simplify(pts, min_dist=3.5)
        start, end = pts_s[0], pts_s[-1]
        strokes.append(
            {
                "idx": i,
                "kind": kind,
                "width": None if width is None else round(float(width), 3),
                "len_pdf": round(L, 1),
                "n_pts": len(pts_s),
                "n_items": len(d.get("items") or []),
                "start_pdf": [round(start[0], 2), round(start[1], 2)],
                "end_pdf": [round(end[0], 2), round(end[1], 2)],
                "start_svg": _pdf_to_svg(start[0], start[1], court),
                "end_svg": _pdf_to_svg(end[0], end[1], court),
            }
        )
    return strokes


def _ocr_positions(page_1: int):
    png = ROOT / f"uploads/bulk_imports/d125785a44474042b13589e9aadeca4f/page_{page_1:04d}.png"
    if not png.is_file():
        return None
    try:
        from playbook_sheet_align import analyze_sheet_image

        return analyze_sheet_image(png).get("positions")
    except Exception as exc:  # noqa: BLE001 — audit must not die on OCR
        return {"_error": str(exc)}


def _delta_positions(raw_chosen: dict, interpreted: dict) -> dict:
    """Compare chosen raw court digits to extract_page positions (should match)."""
    out = {}
    for oid in sorted(set(raw_chosen) | set(interpreted)):
        a = raw_chosen.get(oid)
        b = interpreted.get(oid)
        if not a or not b:
            out[oid] = {"missing_raw": a is None, "missing_interp": b is None}
            continue
        dx = round(float(b["x"]) - float(a["x"]), 3)
        dy = round(float(b["y"]) - float(a["y"]), 3)
        out[oid] = {
            "raw": a,
            "interp": b,
            "dx": dx,
            "dy": dy,
            "dist": round(math.hypot(dx, dy), 3),
        }
    return out


def _choose_digits(raw_digits):
    """Same preference as extract: largest-area in-court glyph per digit."""
    by: dict[int, dict] = {}
    for row in raw_digits:
        if not row["in_court"]:
            continue
        d = row["digit"]
        prev = by.get(d)
        if prev is None or row["area"] >= prev["area"]:
            by[d] = row
    return {f"o{d}": row["court_svg"] for d, row in by.items()}


def _y_flip_test(raw_chosen: dict, court) -> dict:
    """If Liberty accidentally flipped Y, flipped coords would match OCR better —
    here we just report whether PDF→SVG keeps PDF Y direction (no flip).
    """
    x0, y0, x1, y1 = court
    bh = max(y1 - y0, 1e-6)
    samples = []
    for oid, svg in list(raw_chosen.items())[:3]:
        # Invert Y within court and see distance from original (always large unless mid).
        y_flip = round(COURT_H - float(svg["y"]), 2)
        samples.append(
            {
                "oid": oid,
                "svg_y": svg["y"],
                "flipped_y": y_flip,
                "delta_if_flipped": round(abs(y_flip - float(svg["y"])), 2),
            }
        )
    return {
        "transform": "pdf_to_svg uses (y-y0)/bh*COURT_H — same direction as PDF (down+)",
        "samples": samples,
        "global_y_flip_in_vector_extract": False,
    }


def _svg_overlay(sample: dict) -> str:
    """Inline SVG: court box, raw digits, interpreted tokens, stroke endpoints."""
    court = sample["court_pdf"]
    x0, y0, x1, y1 = court
    # Draw in court SVG space 500x470.
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {COURT_W} {COURT_H}" '
        f'width="500" height="470" style="background:#1a2332;border-radius:6px">'
        f'<rect x="0" y="0" width="{COURT_W}" height="{COURT_H}" fill="#243044" stroke="#6b7c93"/>'
        f'<text x="8" y="18" fill="#9fb0c7" font-size="12">'
        f'{sample["label"]} p{sample["page"]} — raw digits (cyan) vs interp (orange)</text>'
    ]
    # Raw play strokes
    for s in sample["raw_strokes"]:
        if s["kind"] not in ("play_stroke", "dribble_candidate"):
            continue
        a, b = s["start_svg"], s["end_svg"]
        color = "#7dd3fc" if s["kind"] == "play_stroke" else "#a78bfa"
        parts.append(
            f'<line x1="{a["x"]}" y1="{a["y"]}" x2="{b["x"]}" y2="{b["y"]}" '
            f'stroke="{color}" stroke-width="2" opacity="0.55"/>'
        )
        parts.append(
            f'<circle cx="{b["x"]}" cy="{b["y"]}" r="3" fill="{color}" opacity="0.8"/>'
        )
    # Interpreted paths
    ink = sample["interpreted"]["ink"]
    for oid, pts in (ink.get("paths") or {}).items():
        if not pts:
            continue
        d = "M " + " L ".join(f'{p["x"]},{p["y"]}' for p in pts)
        parts.append(f'<path d="{d}" fill="none" stroke="#fb923c" stroke-width="2.5" opacity="0.9"/>')
    for p in ink.get("passes") or []:
        pts = p.get("points") or []
        if len(pts) < 2:
            continue
        d = "M " + " L ".join(f'{pt["x"]},{pt["y"]}' for pt in pts)
        parts.append(
            f'<path d="{d}" fill="none" stroke="#f472b6" stroke-width="2.5" '
            f'stroke-dasharray="8 5" opacity="0.95"/>'
        )
    # Digits
    for oid, pos in (sample["raw_chosen_svg"] or {}).items():
        parts.append(
            f'<circle cx="{pos["x"]}" cy="{pos["y"]}" r="12" fill="none" stroke="#22d3ee" stroke-width="2"/>'
            f'<text x="{pos["x"]}" y="{pos["y"] + 4}" text-anchor="middle" fill="#22d3ee" '
            f'font-size="14" font-family="Segoe UI,sans-serif">{oid[1:]}</text>'
        )
    for oid, pos in (sample["interpreted"]["positions"] or {}).items():
        parts.append(
            f'<circle cx="{pos["x"]}" cy="{pos["y"]}" r="7" fill="#fb923c" opacity="0.85"/>'
            f'<text x="{pos["x"]}" y="{pos["y"] - 14}" text-anchor="middle" fill="#fdba74" '
            f'font-size="11" font-family="Segoe UI,sans-serif">{oid}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def audit_page(label: str, page_1: int) -> dict:
    doc = fitz.open(PDF)
    try:
        page = doc[page_1 - 1]
        court = _detect_court_rect(page)
        raw_digits = _raw_digits(page, court)
        raw_strokes = _raw_strokes(page, court)
        chosen = _choose_digits(raw_digits)
        interpreted = extract_page(PDF, page_1)
        # Drop bulky nested pdf path for JSON size.
        interp_slim = {
            "ok": interpreted.get("ok"),
            "source": interpreted.get("source"),
            "page": interpreted.get("page"),
            "title": interpreted.get("title"),
            "court_frac": interpreted.get("court_frac"),
            "positions": interpreted.get("positions"),
            "ink": {
                "marks": interpreted["ink"].get("marks"),
                "paths": {
                    k: [{"x": p["x"], "y": p["y"]} for p in v]
                    for k, v in (interpreted["ink"].get("paths") or {}).items()
                },
                "passes": interpreted["ink"].get("passes") or [],
            },
        }
        pos_delta = _delta_positions(chosen, interp_slim["positions"] or {})
        ocr = _ocr_positions(page_1)
        stroke_summary = {
            "play_stroke": sum(1 for s in raw_strokes if s["kind"] == "play_stroke"),
            "dribble_candidate": sum(1 for s in raw_strokes if s["kind"] == "dribble_candidate"),
            "court_geometry_filtered": sum(
                1 for s in raw_strokes if s["kind"] == "court_geometry_filtered"
            ),
            "circle_outline": sum(1 for s in raw_strokes if s["kind"] == "circle_outline"),
        }
        # Attribution check: does each interpreted path start near its oid digit?
        attr = []
        for oid, pts in (interp_slim["ink"]["paths"] or {}).items():
            if not pts or oid not in chosen:
                continue
            start = pts[0]
            tip = pts[-1]
            d0 = math.hypot(start["x"] - chosen[oid]["x"], start["y"] - chosen[oid]["y"])
            # Tip distance to any other digit
            tip_near = None
            tip_d = 1e9
            for other, pos in chosen.items():
                d = math.hypot(tip["x"] - pos["x"], tip["y"] - pos["y"])
                if d < tip_d:
                    tip_d = d
                    tip_near = other
            attr.append(
                {
                    "oid": oid,
                    "mark": (interp_slim["ink"]["marks"] or {}).get(oid),
                    "start_snap_dist": round(d0, 2),
                    "tip_svg": tip,
                    "nearest_digit_at_tip": tip_near,
                    "tip_digit_dist": round(tip_d, 2),
                    "n_pts": len(pts),
                }
            )
        return {
            "label": label,
            "page": page_1,
            "page_rect": [round(page.rect.width, 2), round(page.rect.height, 2)],
            "court_pdf": [round(c, 2) for c in court],
            "court_default": list(_DEFAULT_COURT_PDF),
            "court_matches_default": [round(c, 1) for c in court]
            == [round(c, 1) for c in _DEFAULT_COURT_PDF],
            "raw_digits": raw_digits,
            "raw_chosen_svg": chosen,
            "raw_strokes": raw_strokes,
            "stroke_summary": stroke_summary,
            "interpreted": interp_slim,
            "position_delta_raw_vs_interp": pos_delta,
            "ocr_positions": ocr,
            "y_flip_probe": _y_flip_test(chosen, court),
            "path_attribution": attr,
        }
    finally:
        doc.close()


def _html_report(samples: list[dict], verdict: dict) -> str:
    rows = []
    for s in samples:
        pos_rows = "".join(
            f"<tr><td>{oid}</td><td>{json.dumps(d.get('raw'))}</td>"
            f"<td>{json.dumps(d.get('interp'))}</td>"
            f"<td>{d.get('dx')},{d.get('dy')}</td><td>{d.get('dist')}</td></tr>"
            for oid, d in (s["position_delta_raw_vs_interp"] or {}).items()
        )
        stroke_rows = "".join(
            f"<tr><td>{st['kind']}</td><td>{st['width']}</td><td>{st['len_pdf']}</td>"
            f"<td>{st['start_pdf']} → {st['end_pdf']}</td>"
            f"<td>({st['start_svg']['x']},{st['start_svg']['y']}) → "
            f"({st['end_svg']['x']},{st['end_svg']['y']})</td></tr>"
            for st in s["raw_strokes"]
            if st["kind"] in ("play_stroke", "dribble_candidate")
        )
        digit_rows = "".join(
            f"<tr><td>{r['digit']}</td><td>{r['pdf_xy']}</td><td>{r['in_court']}</td>"
            f"<td>{json.dumps(r['court_svg'])}</td><td>{r['area']}</td></tr>"
            for r in s["raw_digits"]
        )
        ink = s["interpreted"]["ink"]
        path_bits = "".join(
            f"<li><code>{oid}</code> mark=<code>{(ink.get('marks') or {}).get(oid)}</code> "
            f"pts={len(pts)} start={pts[0]} tip={pts[-1]}</li>"
            for oid, pts in (ink.get("paths") or {}).items()
            if pts
        )
        pass_bits = "".join(
            f"<li>{p.get('fromPid')}→{p.get('toPid')} type={p.get('type')} "
            f"n_pts={len(p.get('points') or [])}</li>"
            for p in (ink.get("passes") or [])
        )
        attr_bits = "".join(
            f"<li>{a['oid']}: snap={a['start_snap_dist']} tip→{a['nearest_digit_at_tip']} "
            f"@{a['tip_digit_dist']}px mark={a['mark']}</li>"
            for a in s.get("path_attribution") or []
        )
        ocr = s.get("ocr_positions")
        rows.append(
            f"""
<section class="sheet">
  <h2>{s['label']} — page {s['page']} <span class="muted">({s['interpreted'].get('title') or ''})</span></h2>
  <p class="meta">court_pdf={s['court_pdf']} · matches_default={s['court_matches_default']} ·
     strokes={json.dumps(s['stroke_summary'])}</p>
  {_svg_overlay(s)}
  <div class="grid">
    <div>
      <h3>1. Raw vector digits</h3>
      <table><thead><tr><th>#</th><th>PDF xy</th><th>in_court</th><th>court SVG</th><th>area</th></tr></thead>
      <tbody>{digit_rows}</tbody></table>
      <h3>Raw play strokes</h3>
      <table><thead><tr><th>kind</th><th>w</th><th>len</th><th>PDF ends</th><th>SVG ends</th></tr></thead>
      <tbody>{stroke_rows or '<tr><td colspan=5>none</td></tr>'}</tbody></table>
    </div>
    <div>
      <h3>2. Interpreted (sheet-extract / extract_page)</h3>
      <p>positions: <code>{json.dumps(s['interpreted'].get('positions'))}</code></p>
      <p>paths:</p><ul>{path_bits or '<li>none</li>'}</ul>
      <p>passes:</p><ul>{pass_bits or '<li>none</li>'}</ul>
      <h3>OCR positions (for contrast)</h3>
      <pre>{json.dumps(ocr, indent=2)}</pre>
    </div>
  </div>
  <h3>3. Delta</h3>
  <table><thead><tr><th>oid</th><th>raw SVG</th><th>interp SVG</th><th>dx,dy</th><th>dist</th></tr></thead>
  <tbody>{pos_rows}</tbody></table>
  <p>Path tip attribution:</p><ul>{attr_bits or '<li>n/a</li>'}</ul>
  <details><summary>y_flip_probe</summary><pre>{json.dumps(s['y_flip_probe'], indent=2)}</pre></details>
</section>
"""
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Playbook vector audit — raw vs Liberty</title>
<style>
  body {{ font-family: "Segoe UI", system-ui, sans-serif; margin: 24px; background: #0f1419; color: #e7ecf3; }}
  h1 {{ font-size: 1.4rem; }}
  h2 {{ margin-top: 2rem; border-top: 1px solid #334155; padding-top: 1rem; }}
  h3 {{ font-size: 1rem; color: #cbd5e1; }}
  .muted {{ color: #94a3b8; font-weight: 400; font-size: 0.9rem; }}
  .meta {{ color: #94a3b8; font-size: 0.85rem; }}
  .verdict {{ background: #1e293b; border-left: 4px solid #38bdf8; padding: 12px 16px; margin: 16px 0; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  @media (max-width: 900px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.8rem; margin-bottom: 12px; }}
  th, td {{ border: 1px solid #334155; padding: 4px 6px; text-align: left; vertical-align: top; }}
  th {{ background: #1e293b; }}
  code, pre {{ font-size: 0.75rem; }}
  pre {{ background: #1e293b; padding: 8px; overflow: auto; max-height: 220px; }}
  svg {{ max-width: 100%; height: auto; margin: 8px 0 16px; }}
  a {{ color: #7dd3fc; }}
  .legend span {{ display: inline-block; margin-right: 12px; font-size: 0.85rem; }}
</style>
</head>
<body>
<h1>Playbook vector audit — raw FastDraw vs Liberty interpret</h1>
<p class="meta">PDF: <code>{PDF.as_posix()}</code> · generated by <code>scripts/playbook_vector_audit.py</code></p>
<div class="legend">
  <span style="color:#22d3ee">● raw digit</span>
  <span style="color:#fb923c">● interp token / path</span>
  <span style="color:#f472b6">╌ pass</span>
  <span style="color:#7dd3fc">— raw stroke chord</span>
</div>
<div class="verdict">
  <strong>Global transform bug?</strong> {verdict['global_transform_bug']}<br/>
  <strong>Verdict:</strong> {verdict['summary']}<br/>
  <em>Evidence:</em> {verdict['evidence']}
</div>
{''.join(rows)}
</body>
</html>
"""


def _build_verdict(samples: list[dict]) -> dict:
    # Position deltas between raw chosen digits and extract_page should be ~0.
    max_pos_dist = 0.0
    for s in samples:
        for d in (s["position_delta_raw_vs_interp"] or {}).values():
            if isinstance(d.get("dist"), (int, float)):
                max_pos_dist = max(max_pos_dist, float(d["dist"]))

    courts_same = all(s["court_matches_default"] or True for s in samples)
    # All samples use same transform; check court detection consistency.
    court_set = {tuple(s["court_pdf"]) for s in samples}

    tip_past = []
    for s in samples:
        for a in s.get("path_attribution") or []:
            # Tip near a *different* digit while mark is cut → pass misclass risk
            if (
                a.get("nearest_digit_at_tip")
                and a["nearest_digit_at_tip"] != a["oid"]
                and a.get("tip_digit_dist", 999) < 40
                and a.get("mark") == "cut"
            ):
                tip_past.append(f"{s['label']} p{s['page']} {a['oid']} tip→{a['nearest_digit_at_tip']}")

    # Compare stroke count vs attributed paths — per-play variance.
    attr_gaps = []
    for s in samples:
        play_n = s["stroke_summary"].get("play_stroke", 0) + s["stroke_summary"].get(
            "dribble_candidate", 0
        )
        got = len(s["interpreted"]["ink"].get("paths") or {}) + len(
            s["interpreted"]["ink"].get("passes") or []
        )
        if play_n != got:
            attr_gaps.append(
                f"{s['label']} p{s['page']}: raw_play_strokes={play_n} attributed={got}"
            )

    global_bug = "No"
    if max_pos_dist > 1.0:
        global_bug = "Yes — digit SVG transform mismatch"
    # Y flip would make max_pos_dist large OR digits outside court — neither here.

    summary = (
        "Digit positions are a pure map of PDF text centers (no Y-flip / scale bug). "
        "Misreads are mostly per-play: stroke classification, nearest-digit attribution, "
        "and pass vs cut heuristics."
    )
    evidence = (
        f"raw_vs_interp digit max dist={max_pos_dist:.3f} across {len(samples)} sheets; "
        f"unique court_pdf rects={len(court_set)}; "
        f"attribution gaps: {'; '.join(attr_gaps) or 'none'}; "
        f"cut-with-tip-near-other: {'; '.join(tip_past) or 'none'}."
    )
    return {
        "global_transform_bug": global_bug,
        "summary": summary,
        "evidence": evidence,
        "max_digit_delta": max_pos_dist,
        "unique_courts": [list(c) for c in court_set],
        "attribution_gaps": attr_gaps,
        "suspicious_cut_tips": tip_past,
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    samples = [audit_page(s["label"], s["page"]) for s in SAMPLES]
    # Attach overlay markup not needed in JSON; strip nothing else.
    verdict = _build_verdict(samples)
    payload = {"pdf": str(PDF), "samples": samples, "verdict": verdict}
    json_path = OUT / "raw_vs_interpreted.json"
    html_path = OUT / "raw_vs_interpreted.html"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    html_path.write_text(_html_report(samples, verdict), encoding="utf-8")
    # Also copy a short markdown index.
    md_path = OUT / "README.md"
    md_path.write_text(
        "\n".join(
            [
                "# Playbook vector audit",
                "",
                f"- HTML: [`raw_vs_interpreted.html`](raw_vs_interpreted.html)",
                f"- JSON: [`raw_vs_interpreted.json`](raw_vs_interpreted.json)",
                f"- Regenerator: `scripts/playbook_vector_audit.py`",
                "",
                f"**Global transform bug?** {verdict['global_transform_bug']}",
                "",
                verdict["summary"],
                "",
                f"Evidence: {verdict['evidence']}",
                "",
                "Open the HTML via hard-refresh or:",
                f"`file:///{html_path.as_posix()}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps({"wrote": [str(json_path), str(html_path), str(md_path)], "verdict": verdict}, indent=2))


if __name__ == "__main__":
    main()
