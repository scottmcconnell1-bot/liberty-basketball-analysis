#!/usr/bin/env python3
"""Quick teach/ops status for Scott and agents (live + panel gates).

Examples:
  py -3.12 scripts/teach_ops_status.py
  py -3.12 scripts/teach_ops_status.py --refresh-learning
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--refresh-learning",
        action="store_true",
        help="Also regenerate docs/LEARNING_STATUS.md",
    )
    args = ap.parse_args()

    print("=== detached --status ===")
    rc = subprocess.call(
        [PY, str(ROOT / "scripts" / "start_hoops_teach_detached.py"), "--status"],
        cwd=str(ROOT),
    )
    print(f"(status rc={rc})")

    log = ROOT / "data" / "hoopsalytics" / "detached_teach_loop.out.log"
    if log.exists():
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
        print("\n=== teach log (tail 12) ===")
        for ln in lines[-12:]:
            print(ln)

    latest = ROOT / "data" / "hoopsalytics" / "full_film_panel_latest.json"
    if latest.exists():
        try:
            data = json.loads(latest.read_text(encoding="utf-8"))
            ev = data.get("evaluation") or {}
            overall = "PASS" if ev.get("overall_pass") else "FAIL"
            print(
                f"\n=== panel === overall={overall} "
                f"P={ev.get('mean_precision')} R={ev.get('mean_recall')}"
            )
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            print(f"\n=== panel === could not read: {exc}")

    if args.refresh_learning:
        print("\n=== generate_learning_status ===")
        subprocess.call([PY, str(ROOT / "scripts" / "generate_learning_status.py")], cwd=str(ROOT))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
