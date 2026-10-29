"""Score auto-built choreography against the hand-made choreography files.

Plan: .team/specs/12_numbered_lines_plan.md, Stage 1 deliverable 4. N = 15 SVG
court units (court 500 x 470), fixed in the plan before scoring.

Per step (square), compared to the hand file with the same play id:
  players placed   o1..o5 in the hand file whose auto position is within N
  lines matched    hand line <-> auto line, same player, Hausdorff distance <= N
                   (one auto line per hand line; type is NOT required to match,
                   so "type correct" below can be below 100%)
  type correct     of matched lines, same kind (pass/cut/dribble/screen)
  sequence correct of matched lines, same rank in the square's order

A hand file whose steps have no lines is reported but not scored for lines.
A hand file that is a copy of another (same pages) is scored once.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def _dense(pts: list[dict], step: float = 3.0) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    p = [(float(q["x"]), float(q["y"])) for q in pts]
    for a, b in zip(p, p[1:]):
        n = max(1, int(math.dist(a, b) / step))
        out.extend((a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n))
    if p:
        out.append(p[-1])
    return out


def hausdorff(a: list[dict], b: list[dict]) -> float:
    A, B = _dense(a), _dense(b)
    if not A or not B:
        return float("inf")

    def directed(X, Y):
        return max(min(math.dist(x, y) for y in Y) for x in X)

    return max(directed(A, B), directed(B, A))


def _lines(step: dict) -> list[dict]:
    acts = (step.get("ink") or {}).get("actions") or []
    out = []
    for i, a in enumerate(acts):
        out.append(
            {
                "pid": a.get("fromPid") or a.get("pid"),
                "kind": a.get("kind"),
                "seq": a.get("seq", i + 1),
                "points": a.get("points") or [],
            }
        )
    return out


def _ranks(values: list) -> list[int]:
    order = sorted(set(values))
    return [order.index(v) for v in values]


def score_step(hand: dict, auto: dict, tol: float) -> dict:
    hp, ap = hand.get("positions") or {}, auto.get("positions") or {}
    players_total = len(hp)
    placed = sum(
        1
        for oid, pos in hp.items()
        if oid in ap and math.dist((pos["x"], pos["y"]), (ap[oid]["x"], ap[oid]["y"])) <= tol
    )
    H, A = _lines(hand), _lines(auto)
    used: set[int] = set()
    pairs = []
    for h in H:
        best, best_d = None, None
        for j, a in enumerate(A):
            if j in used or a["pid"] != h["pid"]:
                continue
            d = hausdorff(h["points"], a["points"])
            if d <= tol and (best_d is None or d < best_d):
                best, best_d = j, d
        if best is not None:
            used.add(best)
            pairs.append((h, A[best]))
    type_ok = sum(1 for h, a in pairs if h["kind"] == a["kind"])
    hr = _ranks([h["seq"] for h, _ in pairs])
    ar = _ranks([a["seq"] for _, a in pairs])
    seq_ok = sum(1 for x, y in zip(hr, ar) if x == y)
    return {
        "players_total": players_total,
        "players_placed": placed,
        "hand_lines": len(H),
        "auto_lines": len(A),
        "matched": len(pairs),
        "type_ok": type_ok,
        "seq_ok": seq_ok,
    }


def score_play(hand_doc: dict, auto_doc: dict, tol: float) -> dict:
    steps = []
    for i, hs in enumerate(hand_doc.get("steps") or []):
        a = (auto_doc.get("steps") or [])[i] if i < len(auto_doc.get("steps") or []) else {}
        steps.append(score_step(hs, a, tol))
    tot = {k: sum(s[k] for s in steps) for k in steps[0]} if steps else {}
    return {"steps": steps, "total": tot}


def _pct(n: int, d: int) -> str:
    return "n/a" if d == 0 else f"{100.0 * n / d:.0f}%"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--auto-dir", required=True, type=Path)
    ap.add_argument("--hand-dir", required=True, type=Path)
    ap.add_argument("--tolerance", type=float, default=15.0)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)

    rows, seen_pages = [], {}
    for hf in sorted(args.hand_dir.glob("*.json"), key=lambda p: int(p.stem) if p.stem.isdigit() else 0):
        hand = json.loads(hf.read_text(encoding="utf-8"))
        af = args.auto_dir / hf.name
        pages = tuple(s.get("source_image") for s in hand.get("steps") or [])
        if pages in seen_pages:
            rows.append((hf.stem, hand.get("source"), None, f"copy of {seen_pages[pages]}"))
            continue
        seen_pages[pages] = hf.stem
        if not af.is_file():
            rows.append((hf.stem, hand.get("source"), None, "no auto file"))
            continue
        res = score_play(hand, json.loads(af.read_text(encoding="utf-8")), args.tolerance)
        note = "" if res["total"].get("hand_lines") else "hand file has no lines"
        rows.append((hf.stem, hand.get("source"), res, note))

    lines = [
        f"# Numbered lines - scoring report (N = {args.tolerance:g} court units)",
        "",
        "| Play | Hand source | Squares | Players placed | Lines matched | Type correct | Sequence correct | Auto lines | Note |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    grand = {"players_total": 0, "players_placed": 0, "hand_lines": 0, "matched": 0, "type_ok": 0, "seq_ok": 0, "auto_lines": 0}
    for pid, source, res, note in rows:
        if res is None:
            lines.append(f"| {pid} | {source} | | | | | | | {note} |")
            continue
        t = res["total"]
        if t["hand_lines"]:
            for k in grand:
                grand[k] += t[k]
        lines.append(
            f"| {pid} | {source} | {len(res['steps'])} | {t['players_placed']}/{t['players_total']} "
            f"| {t['matched']}/{t['hand_lines']} ({_pct(t['matched'], t['hand_lines'])}) "
            f"| {t['type_ok']}/{t['matched']} ({_pct(t['type_ok'], t['matched'])}) "
            f"| {t['seq_ok']}/{t['matched']} ({_pct(t['seq_ok'], t['matched'])}) | {t['auto_lines']} | {note} |"
        )
    g = grand
    lines += [
        "",
        f"**All scored plays with lines:** players {g['players_placed']}/{g['players_total']}, "
        f"lines matched {g['matched']}/{g['hand_lines']} ({_pct(g['matched'], g['hand_lines'])}), "
        f"type {g['type_ok']}/{g['matched']} ({_pct(g['type_ok'], g['matched'])}), "
        f"sequence {g['seq_ok']}/{g['matched']} ({_pct(g['seq_ok'], g['matched'])}), "
        f"auto lines drawn {g['auto_lines']}",
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
