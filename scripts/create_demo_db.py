"""Build a slim film_analysis.db for the Windows demo package.

Source DB is >100MB mostly due to detections/review_items.
Copies schema + small operational tables; skips heavy AI tables.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "film_analysis.db"

# Tables that make the DB huge — omit row data (keep empty table via schema copy).
SKIP_DATA = {
    "detections",
    "review_items",
    "play_recognitions",
    "provenance_records",
    "track_identity_labels",
    "shot_classifications",
    "sqlite_stat1",
    "sqlite_stat4",
    # Never ship secrets / session material in a coach demo package
    "nfhs_credentials",
    "user_sessions",
    "push_subscriptions",
}

# Prefer these when present (demo still opens with schedule/roster-ish data).
PREFER_COPY = {
    "teams",
    "players",
    "games",
    "scheduled_games",
    "film_tool_games",
    "film_roster_players",
    "videos",
    "video_assets",
    "event_types",
    "event_participants",
    "events",
    "possessions",
    "plays",
    "play_steps",
    "play_categories",
    "playbooks",
    "playbook_plays",
    "users",
    "app_settings",
    "stats",
    "player_minutes",
    "player_effect",
    "clips",
    "clip_tags",
    "module_entitlements",
    "roster_memberships",
}


def build(dest: Path) -> None:
    if not SRC.exists():
        raise SystemExit(f"Source DB missing: {SRC}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()

    src = sqlite3.connect(SRC)
    src.execute("PRAGMA busy_timeout=5000")
    dst = sqlite3.connect(dest)

    # Full schema (including indexes) without row data.
    for row in src.execute(
        "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL "
        "AND type IN ('table','index','trigger') "
        "AND name NOT LIKE 'sqlite_%' "
        "ORDER BY CASE type WHEN 'table' THEN 0 WHEN 'index' THEN 1 ELSE 2 END, name"
    ):
        sql = row[0]
        try:
            dst.execute(sql)
        except sqlite3.Error as exc:
            print(f"  skip schema object: {exc}", file=sys.stderr)

    tables = [
        r[0]
        for r in src.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    ]

    for table in tables:
        if table in SKIP_DATA:
            print(f"  empty (skipped data): {table}")
            continue
        # Copy all small tables; for unknown large ones, copy only if under 500 rows.
        try:
            count = src.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
        except sqlite3.Error as exc:
            print(f"  skip {table}: {exc}")
            continue

        if table not in PREFER_COPY and count > 500:
            print(f"  empty (large unknown): {table} ({count} rows)")
            continue

        cols = [r[1] for r in src.execute(f"PRAGMA table_info([{table}])")]
        col_list = ", ".join(f"[{c}]" for c in cols)
        placeholders = ", ".join("?" for _ in cols)
        rows = src.execute(f"SELECT {col_list} FROM [{table}]").fetchall()
        if rows:
            dst.executemany(
                f"INSERT INTO [{table}] ({col_list}) VALUES ({placeholders})",
                rows,
            )
        print(f"  copied {table}: {len(rows)} rows")

    dst.commit()
    dst.execute("VACUUM")
    dst.close()
    src.close()

    mb = dest.stat().st_size / (1024 * 1024)
    print(f"Wrote {dest} ({mb:.2f} MB)")


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "film_analysis.demo.db"
    build(out)
