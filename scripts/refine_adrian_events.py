#!/usr/bin/env python3
"""Refine Adrian JrHigh AI events against confirmed scorebook (Adrian only)."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adrian_quality import ADRIAN_BASE, apply_quality_to_db  # noqa: E402
from program_mode import program_summary  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=ROOT / "film_analysis.db")
    args = ap.parse_args()
    conn = sqlite3.connect(str(args.db), timeout=120)
    conn.row_factory = sqlite3.Row
    report = apply_quality_to_db(conn, ADRIAN_BASE)
    print(json.dumps(report, indent=2, default=str))
    summary = program_summary(conn, ADRIAN_BASE)
    totals = summary["ledger_box"]["totals"]
    print(
        "ledger",
        {k: totals.get(k) for k in ("pts", "fgm", "fga", "tpm", "ftm", "fta", "reb", "ast", "stl", "blk", "to", "foul")},
    )
    print("canonical", summary.get("canonical_key"))
    print("scorebook_team_pts", (summary.get("scorebook") or {}).get("team_pts"))
    print("exceptions", summary["exception_count"])
    for e in summary["exceptions"][:8]:
        msg = e["message"].replace("\u2248", "~")
        print("-", msg.encode("ascii", "replace").decode("ascii"))
    conn.close()
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
