#!/usr/bin/env python3
"""Wipe AI events and rebuild from detections using the hoop/net track.

Does not copy Film Tool tags onto the ledger. Does not retrain ball_detector.pt.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

GAME = "jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334"
DB = ROOT / "film_analysis.db"


def main() -> int:
    import event_generator as eg

    # Fair hoop-rule rebuild: do not stamp tags onto nearby AI rows.
    eg._reapply_film_tool_teach = lambda *a, **k: None

    def _conn(db_path):
        conn = sqlite3.connect(db_path, timeout=120)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout = 120000")
        return conn

    eg.get_db_connection = _conn

    conn = sqlite3.connect(str(DB), timeout=60)
    conn.execute("PRAGMA busy_timeout=60000")
    before = conn.execute(
        "SELECT source_type, COUNT(*) FROM events WHERE game_id=? GROUP BY source_type",
        (GAME,),
    ).fetchall()
    print({"events_before": dict(before)}, flush=True)
    conn.execute(
        "DELETE FROM events WHERE game_id=? AND IFNULL(source_type,'ai')='ai'",
        (GAME,),
    )
    conn.commit()
    after_del = conn.execute(
        "SELECT source_type, COUNT(*) FROM events WHERE game_id=? GROUP BY source_type",
        (GAME,),
    ).fetchall()
    det_n = conn.execute(
        "SELECT COUNT(*) FROM detections WHERE game_id=?",
        (GAME,),
    ).fetchone()[0]
    row = conn.execute(
        "SELECT game_id FROM analysis_runs WHERE analysis_key=? ORDER BY id DESC LIMIT 1",
        (GAME,),
    ).fetchone()
    relational = row[0] if row else None
    conn.close()
    print({"events_after_wipe": dict(after_del), "detections": det_n, "relational": relational}, flush=True)

    ok = eg.main(GAME, str(DB), relational_game_id=relational, mode_override="precision")
    conn = sqlite3.connect(str(DB), timeout=60)
    after = conn.execute(
        "SELECT source_type, COUNT(*) FROM events WHERE game_id=? GROUP BY source_type",
        (GAME,),
    ).fetchall()
    conn.close()
    print({"ok": ok, "events_after": dict(after)}, flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
