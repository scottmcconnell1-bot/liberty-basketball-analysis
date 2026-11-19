"""Measure existing AI shot-finder rows against Scott's manual tags (read-only).

Spec: .team/specs/32_find_shots_measure_spec.md
VETTED conditions 1-5 OVERRIDE the body: read finder rows already in the DB
(source_type='ai', event_type='shot', details_json has 'generator'); do not rerun
event_generator; open sqlite uri mode=ro; Notus extras only inside Q1 span;
report median/max |delta| and n<=1000 / n<=3000; scoreboard rises from saved
file against MAKE tags only (else 'not measured').

No core imports. No video. No DB writes. applied_to_core stays false.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PIXEL_MISS = HERE / "pixel_miss"

# MATCH_TOLERANCE_MS = 8000 in manual_tag_teach.py (line 18). Do not import that core file.
DEFAULT_WINDOW_MS = 8000

# scoreboard_pair_rises.py WINDOW_MS — used only for scoreboard-rise measurement.
SCOREBOARD_WINDOW_MS = 25_000

ADRIAN_GAME_ID = (
    "jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20261006_033941"
)
ADRIAN_TAGS_REL = (
    "data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json"
)
NOTUS_GAME_ID = "jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334"
NOTUS_TAGS_REL = (
    "data/film_tags/jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334.json"
)

KIND_ORDER = ("2PT", "3PT", "FT", "all")
FINDER_KIND_TO_REPORT = {
    "2": "2PT",
    "3": "3PT",
    "ft": "FT",
    "FT": "FT",
    "2PT": "2PT",
    "3PT": "3PT",
}

DEFAULT_OUT_CANDIDATES = [
    Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs\find_shots"),
    Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/find_shots"),
]

SCOREBOARD_RISES_CANDIDATES = [
    Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs\scoreboard\pairs_results.json"),
    Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/scoreboard/pairs_results.json"),
]


# ---------------------------------------------------------------------------
# Pure matching / summary / span helpers
# ---------------------------------------------------------------------------


def match_shots(
    tag_times: Sequence[int],
    finder_times: Sequence[int],
    window_ms: int,
) -> Dict[str, Any]:
    """Greedy nearest-neighbor one-to-one matching within window_ms (spec 2.3).

    Sort all (tag, finder) pairs by |delta|, take closest first, remove both,
    repeat. Returns:
      matches: [(tag_t, finder_t, delta_ms), ...]  where delta_ms = finder_t - tag_t
      unmatched_tags: [...]
      unmatched_finder: [...]
    """
    tag_items = list(enumerate(int(t) for t in tag_times))
    finder_items = list(enumerate(int(t) for t in finder_times))
    pairs: List[Tuple[int, int, int, int, int, int]] = []
    for ti, tt in tag_items:
        for fi, ft in finder_items:
            abs_d = abs(ft - tt)
            if abs_d <= window_ms:
                pairs.append((abs_d, ti, fi, tt, ft, ft - tt))
    pairs.sort(key=lambda p: (p[0], p[1], p[2]))

    used_tags: set[int] = set()
    used_finders: set[int] = set()
    matches: List[Tuple[int, int, int]] = []
    for _abs_d, ti, fi, tt, ft, delta in pairs:
        if ti in used_tags or fi in used_finders:
            continue
        used_tags.add(ti)
        used_finders.add(fi)
        matches.append((tt, ft, delta))

    matches.sort(key=lambda m: (m[0], m[1]))
    unmatched_tags = [tt for ti, tt in tag_items if ti not in used_tags]
    unmatched_finder = [ft for fi, ft in finder_items if fi not in used_finders]
    return {
        "matches": matches,
        "unmatched_tags": unmatched_tags,
        "unmatched_finder": unmatched_finder,
    }


def match_shot_indices(
    tag_times: Sequence[int],
    finder_times: Sequence[int],
    window_ms: int,
) -> Dict[str, Any]:
    """Same greedy rule as match_shots, but returns indices for row identity."""
    tag_items = list(enumerate(int(t) for t in tag_times))
    finder_items = list(enumerate(int(t) for t in finder_times))
    pairs: List[Tuple[int, int, int, int]] = []
    for ti, tt in tag_items:
        for fi, ft in finder_items:
            abs_d = abs(ft - tt)
            if abs_d <= window_ms:
                pairs.append((abs_d, ti, fi, ft - tt))
    pairs.sort(key=lambda p: (p[0], p[1], p[2]))

    used_tags: set[int] = set()
    used_finders: set[int] = set()
    matches: List[Tuple[int, int, int]] = []
    for _abs_d, ti, fi, delta in pairs:
        if ti in used_tags or fi in used_finders:
            continue
        used_tags.add(ti)
        used_finders.add(fi)
        matches.append((ti, fi, delta))

    matches.sort(key=lambda m: (m[0], m[1]))
    return {
        "matches": matches,
        "unmatched_tags": [ti for ti, _ in tag_items if ti not in used_tags],
        "unmatched_finder": [fi for fi, _ in finder_items if fi not in used_finders],
    }


def summarize(
    matches: Sequence[Tuple[Any, ...]],
    *,
    n_tagged: int,
    n_extra: int,
    delta_index: int = 2,
) -> Dict[str, Any]:
    """Counts, recall, precision, median/max |delta|, n<=1000, n<=3000."""
    found = len(matches)
    abs_deltas = [abs(int(m[delta_index])) for m in matches]
    recall = (found / n_tagged) if n_tagged else None
    precision = (found / (found + n_extra)) if (found + n_extra) else None
    return {
        "tagged": n_tagged,
        "found": found,
        "extra": n_extra,
        "recall": recall,
        "precision": precision,
        "median_abs_delta_ms": (
            int(statistics.median(abs_deltas)) if abs_deltas else None
        ),
        "max_abs_delta_ms": max(abs_deltas) if abs_deltas else None,
        "n_abs_delta_le_1000": sum(1 for d in abs_deltas if d <= 1000),
        "n_abs_delta_le_3000": sum(1 for d in abs_deltas if d <= 3000),
    }


def span_bounds(times: Sequence[int], window_ms: int) -> Optional[Tuple[int, int]]:
    """Inclusive span = min(times)-window .. max(times)+window. None if empty."""
    if not times:
        return None
    lo = min(int(t) for t in times)
    hi = max(int(t) for t in times)
    return (lo - int(window_ms), hi + int(window_ms))


def filter_by_span(
    rows: Sequence[Dict[str, Any]],
    t_min: int,
    t_max: int,
    *,
    time_key: str = "t",
) -> List[Dict[str, Any]]:
    """Keep rows whose time_key is inside [t_min, t_max] inclusive."""
    out: List[Dict[str, Any]] = []
    for row in rows:
        t = int(row[time_key])
        if t_min <= t <= t_max:
            out.append(row)
    return out


def report_kind_of_finder(shot_kind: Any) -> Optional[str]:
    if shot_kind is None:
        return None
    return FINDER_KIND_TO_REPORT.get(str(shot_kind).strip())


# ---------------------------------------------------------------------------
# IO helpers (CLI)
# ---------------------------------------------------------------------------


def default_out_dir() -> Path:
    for cand in DEFAULT_OUT_CANDIDATES:
        parent = cand.parent
        if parent.exists():
            return cand
    return DEFAULT_OUT_CANDIDATES[-1]


def pick_existing(*candidates: Path) -> Optional[Path]:
    for cand in candidates:
        if cand is not None and Path(cand).exists():
            return Path(cand)
    return None


def load_shot_tags(tags_path: Path) -> List[Dict[str, Any]]:
    """Load shot tags via measure_net_moved.load_shot_tags (lines 73-97).

    Imported lazily so pure-function tests do not pull net_detector / ai_bridge.
    """
    if str(PIXEL_MISS) not in sys.path:
        sys.path.insert(0, str(PIXEL_MISS))
    from measure_net_moved import load_shot_tags as _load  # noqa: WPS433

    return _load(Path(tags_path))


def open_db_readonly(db_path: Path) -> sqlite3.Connection:
    resolved = Path(db_path).resolve()
    uri = resolved.as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True)


def load_finder_rows(conn: sqlite3.Connection, game_id: str) -> List[Dict[str, Any]]:
    """AI shot rows whose details_json carries a 'generator' key (cond. 1)."""
    cur = conn.execute(
        """
        SELECT id, timestamp_ms, details_json
        FROM events
        WHERE source_type = 'ai'
          AND event_type = 'shot'
          AND game_id = ?
        """,
        (game_id,),
    )
    rows: List[Dict[str, Any]] = []
    for event_id, timestamp_ms, details_json in cur.fetchall():
        try:
            details = json.loads(details_json or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(details, dict) or "generator" not in details:
            continue
        rows.append(
            {
                "id": int(event_id),
                "t": int(timestamp_ms),
                "generator": details.get("generator"),
                "shot_kind": details.get("shot_kind"),
                "details": details,
            }
        )
    return rows


def load_scoreboard_rise_times(path: Path) -> Optional[List[int]]:
    """Return rise times from pairs_results.json, or None if format lacks them."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rises = data.get("rises")
    if not isinstance(rises, list) or not rises:
        return None
    times: List[int] = []
    for rise in rises:
        if not isinstance(rise, dict) or "t" not in rise:
            return None
        times.append(int(rise["t"]))
    return times


def filter_tags_quarters(
    tags: Sequence[Dict[str, Any]], quarters: Iterable[str]
) -> List[Dict[str, Any]]:
    wanted = set(quarters)
    return [t for t in tags if t.get("quarter") in wanted]


def metrics_for_kind(
    tags: Sequence[Dict[str, Any]],
    finders: Sequence[Dict[str, Any]],
    index_match: Dict[str, Any],
    kind: str,
) -> Dict[str, Any]:
    """Recall by TAG kind; extras by finder shot_kind. 'all' uses every row."""
    tag_index = {i for i, tag in enumerate(tags) if kind == "all" or tag.get("eventtype") == kind}
    finder_index = set()
    for i, row in enumerate(finders):
        if kind == "all":
            finder_index.add(i)
        else:
            if report_kind_of_finder(row.get("shot_kind")) == kind:
                finder_index.add(i)

    kind_matches = [m for m in index_match["matches"] if m[0] in tag_index]
    # Spec: extras = finder shots with no matching tag. A finder matched to any
    # tag is not extra. Extras for kind = unmatched finders whose shot_kind maps
    # to kind. Recall for kind = matched tags of that TAG kind / tagged of kind.
    unmatched_finders_of_kind = [
        fi for fi in index_match["unmatched_finder"] if fi in finder_index
    ]
    n_tagged = len(tag_index)
    n_extra = len(unmatched_finders_of_kind)
    triples = [
        (tags[ti]["t"], finders[fi]["t"], delta) for ti, fi, delta in kind_matches
    ]
    return summarize(triples, n_tagged=n_tagged, n_extra=n_extra)


def measure_part(
    tags: List[Dict[str, Any]],
    finders_all: List[Dict[str, Any]],
    window_ms: int,
    *,
    span_note: str,
) -> Dict[str, Any]:
    tag_times = [int(t["t"]) for t in tags]
    bounds = span_bounds(tag_times, window_ms)
    if bounds is None:
        finders: List[Dict[str, Any]] = []
        span = None
    else:
        span = {"t_min": bounds[0], "t_max": bounds[1], "note": span_note}
        finders = filter_by_span(finders_all, bounds[0], bounds[1], time_key="t")

    generators = sorted(
        {str(r["generator"]) for r in finders if r.get("generator") is not None}
    )
    generator_keys = generators + ["all"]

    per_generator: Dict[str, Any] = {}
    tag_match_all: Dict[int, Dict[str, Any]] = {}

    for gen in generator_keys:
        if gen == "all":
            subset = finders
        else:
            subset = [r for r in finders if str(r.get("generator")) == gen]
        idx = match_shot_indices(
            [int(t["t"]) for t in tags],
            [int(r["t"]) for r in subset],
            window_ms,
        )
        kind_metrics = {
            kind: metrics_for_kind(tags, subset, idx, kind) for kind in KIND_ORDER
        }
        per_generator[gen] = {
            "n_finder": len(subset),
            "kinds": kind_metrics,
        }
        if gen == "all":
            for ti, fi, delta in idx["matches"]:
                row = subset[fi]
                tag_match_all[ti] = {
                    "id": row["id"],
                    "time": row["t"],
                    "generator": row["generator"],
                    "shot_kind": row.get("shot_kind"),
                    "delta_ms": delta,
                }

    tag_rows = []
    for i, tag in enumerate(tags):
        tag_rows.append(
            {
                "t": tag["t"],
                "quarter": tag.get("quarter"),
                "eventtype": tag.get("eventtype"),
                "result": tag.get("result"),
                "label": tag.get("label"),
                "player": tag.get("player"),
                "start": tag.get("start"),
                "match": tag_match_all.get(i),
            }
        )

    return {
        "span": span,
        "n_tags": len(tags),
        "n_finder_in_span": len(finders),
        "generators": per_generator,
        "tags": tag_rows,
    }


def format_pct(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{100.0 * value:.1f}%"


def write_summary_md(results: Dict[str, Any], path: Path) -> None:
    lines: List[str] = []
    lines.append("# Find shots — measure what exists")
    lines.append("")
    lines.append(f"Window: **{results['window_ms']} ms** "
                 f"(MATCH_TOLERANCE_MS in manual_tag_teach.py; not imported).")
    lines.append("")
    lines.append(
        "Finder rows: `source_type='ai' AND event_type='shot'` with "
        "`details_json` key `generator`. DB opened read-only."
    )
    lines.append("")

    for part_name, part in results["parts"].items():
        lines.append(f"## {part_name}")
        lines.append("")
        span = part.get("span")
        if span:
            lines.append(
                f"Span (first tag − window .. last tag + window): "
                f"{span['t_min']} .. {span['t_max']} ms. {span.get('note', '')}"
            )
        else:
            lines.append("Span: empty (no tags).")
        lines.append("")
        lines.append(
            f"Tags: {part['n_tags']}; finder rows in span: {part['n_finder_in_span']}."
        )
        lines.append("")

        for gen, gen_block in part["generators"].items():
            lines.append(f"### Generator: `{gen}` (n={gen_block['n_finder']})")
            lines.append("")
            lines.append(
                "| Kind | Tagged | Found | Extra | Recall | Precision | "
                "Median |Δ| ms | Max |Δ| ms | n≤1000 | n≤3000 |"
            )
            lines.append(
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
            )
            for kind in KIND_ORDER:
                m = gen_block["kinds"][kind]
                lines.append(
                    "| {kind} | {tagged} | {found} | {extra} | {recall} | {prec} | "
                    "{med} | {mx} | {n1} | {n3} |".format(
                        kind=kind,
                        tagged=m["tagged"],
                        found=m["found"],
                        extra=m["extra"],
                        recall=format_pct(m["recall"]),
                        prec=format_pct(m["precision"]),
                        med=m["median_abs_delta_ms"]
                        if m["median_abs_delta_ms"] is not None
                        else "—",
                        mx=m["max_abs_delta_ms"]
                        if m["max_abs_delta_ms"] is not None
                        else "—",
                        n1=m["n_abs_delta_le_1000"],
                        n3=m["n_abs_delta_le_3000"],
                    )
                )
            lines.append("")

    lines.append("## Scoreboard rises")
    lines.append("")
    sb = results.get("scoreboard_rises")
    if sb == "not measured" or sb is None:
        lines.append("not measured")
    else:
        lines.append(
            f"Source: `{sb['source']}`. Matched against MAKE tags only. "
            f"Window {sb['window_ms']} ms (scoreboard_pair_rises.py WINDOW_MS)."
        )
        lines.append("")
        m = sb["summary"]
        lines.append(
            f"- Makes tagged: {m['tagged']}; found: {m['found']}; "
            f"extra rises: {m['extra']}"
        )
        lines.append(
            f"- Recall {format_pct(m['recall'])}; precision {format_pct(m['precision'])}"
        )
        lines.append(
            f"- Median |Δ| {m['median_abs_delta_ms']}; max |Δ| {m['max_abs_delta_ms']}; "
            f"n≤1000 {m['n_abs_delta_le_1000']}; n≤3000 {m['n_abs_delta_le_3000']}"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def run_measure(
    *,
    db_path: Path,
    out_dir: Path,
    window_ms: int,
    root: Path = ROOT,
) -> Dict[str, Any]:
    if out_dir.exists():
        raise SystemExit(f"Refuse: output directory already exists: {out_dir}")

    adrian_tags = load_shot_tags(root / ADRIAN_TAGS_REL)
    notus_tags = load_shot_tags(root / NOTUS_TAGS_REL)

    conn = open_db_readonly(db_path)
    try:
        adrian_finders = load_finder_rows(conn, ADRIAN_GAME_ID)
        notus_finders = load_finder_rows(conn, NOTUS_GAME_ID)
    finally:
        conn.close()

    parts_spec = [
        (
            "Adrian Q1-Q3",
            filter_tags_quarters(adrian_tags, {"Q1", "Q2", "Q3"}),
            adrian_finders,
            "Adrian Q1–Q3: extras only inside this part's tag span.",
        ),
        (
            "Adrian Q4",
            filter_tags_quarters(adrian_tags, {"Q4"}),
            adrian_finders,
            "Adrian Q4: tags with quarter Q4; finder rows in Q4 span (cond. 2).",
        ),
        (
            "Notus Q1",
            filter_tags_quarters(notus_tags, {"Q1", "Q2", "Q3", "Q4"}),
            notus_finders,
            "Notus tags cover Q1 only; extras counted only inside Q1 span "
            "(first tag − window .. last tag + window) (cond. 2).",
        ),
    ]

    parts: Dict[str, Any] = {}
    for name, tags, finders, note in parts_spec:
        parts[name] = measure_part(tags, finders, window_ms, span_note=note)

    # Scoreboard rises (cond. 4) — Adrian MAKE tags vs saved rise times.
    rises_path = pick_existing(*SCOREBOARD_RISES_CANDIDATES)
    if rises_path is None:
        scoreboard: Any = "not measured"
    else:
        rise_times = load_scoreboard_rise_times(rises_path)
        if rise_times is None:
            scoreboard = "not measured"
        else:
            make_times = [
                int(t["t"]) for t in adrian_tags if t.get("result") == "Make"
            ]
            matched = match_shots(make_times, rise_times, SCOREBOARD_WINDOW_MS)
            scoreboard = {
                "source": str(rises_path),
                "window_ms": SCOREBOARD_WINDOW_MS,
                "n_rises": len(rise_times),
                "summary": summarize(
                    matched["matches"],
                    n_tagged=len(make_times),
                    n_extra=len(matched["unmatched_finder"]),
                ),
                "matches": [
                    {"tag_t": a, "rise_t": b, "delta_ms": d}
                    for a, b, d in matched["matches"]
                ],
            }

    results = {
        "applied_to_core": False,
        "window_ms": window_ms,
        "db": str(db_path),
        "adrian_game_id": ADRIAN_GAME_ID,
        "notus_game_id": NOTUS_GAME_ID,
        "parts": parts,
        "scoreboard_rises": scoreboard,
    }

    out_dir.mkdir(parents=True, exist_ok=False)
    (out_dir / "results.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8"
    )
    write_summary_md(results, out_dir / "summary.md")
    return results


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Measure existing AI shot finders against manual tags (read-only)."
    )
    p.add_argument(
        "--db",
        type=Path,
        default=ROOT / "film_analysis.db",
        help="Path to film_analysis.db (opened read-only).",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory (refused if it already exists). "
        "Default: Liberty_Shot_Outputs/find_shots",
    )
    p.add_argument(
        "--window-ms",
        type=int,
        default=DEFAULT_WINDOW_MS,
        help="Match window ms (default 8000 = MATCH_TOLERANCE_MS in manual_tag_teach.py).",
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    out_dir = args.out_dir if args.out_dir is not None else default_out_dir()
    run_measure(db_path=args.db, out_dir=out_dir, window_ms=args.window_ms)
    print(f"Wrote {out_dir / 'results.json'} and {out_dir / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
