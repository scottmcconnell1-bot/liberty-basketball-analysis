#!/usr/bin/env python3
"""
One-time data migration: clamp detection coordinates to frame bounds.

The Riverstone video (1920x1080) was processed before the YOLO clamping fix,
so many detections have x_center > 1919 and/or y_center > 1079. This script
clamps those coordinates back to valid frame bounds.

Only the `detections` table is touched. No other tables or columns are modified.
"""

import sqlite3
import sys

DB_PATH = "film_analysis.db"
GAME_ID = "riverstone_Liberty_Vs_Riverstone_20260519_103815"
FRAME_W = 1920
FRAME_H = 1080
X_MAX = FRAME_W - 1  # 1919
Y_MAX = FRAME_H - 1  # 1079


def main():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout = 30000")

    # ── Before stats ──────────────────────────────────────────
    total = conn.execute(
        "SELECT COUNT(*) FROM detections WHERE game_id = ?", (GAME_ID,)
    ).fetchone()[0]

    before = conn.execute(
        """
        SELECT
            MIN(x_center) AS min_x, MAX(x_center) AS max_x, AVG(x_center) AS avg_x,
            MIN(y_center) AS min_y, MAX(y_center) AS max_y, AVG(y_center) AS avg_y,
            SUM(CASE WHEN x_center < 0 OR x_center > ? THEN 1 ELSE 0 END) AS x_oob,
            SUM(CASE WHEN y_center < 0 OR y_center > ? THEN 1 ELSE 0 END) AS y_oob
        FROM detections WHERE game_id = ?
        """,
        (X_MAX, Y_MAX, GAME_ID),
    ).fetchone()

    print("=" * 60)
    print("DETECTION COORDINATE MIGRATION")
    print("=" * 60)
    print(f"Game:       {GAME_ID}")
    print(f"Frame size: {FRAME_W}x{FRAME_H}")
    print(f"Total rows: {total}")
    print()
    print("── BEFORE ──")
    print(f"  x_center:  min={before[0]}, max={before[1]}, avg={before[2]:.1f}")
    print(f"  y_center:  min={before[3]}, max={before[4]}, avg={before[5]:.1f}")
    print(f"  Out-of-bounds: x_center={before[6]}, y_center={before[7]}")

    if before[6] == 0 and before[7] == 0:
        print("\n✅ No out-of-bounds coordinates found. Nothing to do.")
        conn.close()
        return

    # ── Clamp coordinates ─────────────────────────────────────
    # Clamp x_center to [0, X_MAX] and y_center to [0, Y_MAX]
    cursor = conn.execute(
        """
        UPDATE detections
        SET x_center = CASE
                WHEN x_center < 0 THEN 0
                WHEN x_center > ? THEN ?
                ELSE x_center
            END,
            y_center = CASE
                WHEN y_center < 0 THEN 0
                WHEN y_center > ? THEN ?
                ELSE y_center
            END
        WHERE game_id = ?
          AND (x_center < 0 OR x_center > ?
             OR y_center < 0 OR y_center > ?)
        """,
        (X_MAX, X_MAX, Y_MAX, Y_MAX, GAME_ID, X_MAX, Y_MAX),
    )
    updated = cursor.rowcount
    conn.commit()

    print(f"\n  Rows updated: {updated}")

    # ── After stats ───────────────────────────────────────────
    after = conn.execute(
        """
        SELECT
            MIN(x_center) AS min_x, MAX(x_center) AS max_x, AVG(x_center) AS avg_x,
            MIN(y_center) AS min_y, MAX(y_center) AS max_y, AVG(y_center) AS avg_y,
            SUM(CASE WHEN x_center < 0 OR x_center > ? THEN 1 ELSE 0 END) AS x_oob,
            SUM(CASE WHEN y_center < 0 OR y_center > ? THEN 1 ELSE 0 END) AS y_oob
        FROM detections WHERE game_id = ?
        """,
        (X_MAX, Y_MAX, GAME_ID),
    ).fetchone()

    print()
    print("── AFTER ──")
    print(f"  x_center:  min={after[0]}, max={after[1]}, avg={after[2]:.1f}")
    print(f"  y_center:  min={after[3]}, max={after[4]}, avg={after[5]:.1f}")
    print(f"  Out-of-bounds: x_center={after[6]}, y_center={after[7]}")

    # ── Verify ────────────────────────────────────────────────
    if after[6] == 0 and after[7] == 0:
        print("\n✅ All coordinates now within frame bounds.")
    else:
        print(f"\n⚠️  WARNING: {after[6] + after[7]} out-of-bounds values remain!")
        sys.exit(1)

    conn.close()
    print("=" * 60)
    print("Migration complete.")


if __name__ == "__main__":
    main()
