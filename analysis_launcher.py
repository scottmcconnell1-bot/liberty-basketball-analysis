#!/usr/bin/env python
"""Launch ai_analyzer.py and report startup failures to analysis_runs."""

from __future__ import annotations

import sqlite3
import sys
import traceback


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=60.0)
    conn.execute("PRAGMA busy_timeout=60000")
    return conn


def _mark_failed(db_path: str, game_id: str, message: str) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """UPDATE analysis_runs
               SET status='failed',
                   error_message=?,
                   completed_at=CURRENT_TIMESTAMP
               WHERE analysis_key=? AND status IN ('pending', 'running')""",
            (message[:500], game_id),
        )
        try:
            conn.execute(
                """UPDATE analysis_runs
                   SET progress_step='Failed'
                   WHERE analysis_key=? AND status='failed'""",
                (game_id,),
            )
        except sqlite3.OperationalError:
            pass
        conn.commit()
    finally:
        conn.close()


def _mark_running(db_path: str, game_id: str) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """UPDATE analysis_runs
               SET status='running',
               started_at=CURRENT_TIMESTAMP
               WHERE analysis_key=? AND status='pending'""",
            (game_id,),
        )
        try:
            conn.execute(
                """UPDATE analysis_runs
                   SET progress_pct=0, progress_step='Loading AI models…'
                   WHERE analysis_key=? AND status='running'""",
                (game_id,),
            )
        except sqlite3.OperationalError:
            pass
        conn.commit()
    finally:
        conn.close()


def main() -> int:
    if len(sys.argv) != 4:
        print("Usage: analysis_launcher.py <db_path> <video_path> <game_id>")
        return 2

    db_path, video_path, game_id = sys.argv[1], sys.argv[2], sys.argv[3]
    try:
        _mark_running(db_path, game_id)
        import runpy

        from app import app

        sys.argv = ["ai_analyzer.py", db_path, video_path, game_id]
        # Workers are not HTTP requests; push app context so auto_accept →
        # refresh_game_stats → feature_enabled / current_app paths work.
        with app.app_context():
            runpy.run_path("ai_analyzer.py", run_name="__main__")
        return 0
    except SystemExit as exc:
        code = exc.code if exc.code is not None else 0
        if code not in (0, None):
            _mark_failed(db_path, game_id, f"Analysis worker exited with code {code}")
        raise
    except Exception as exc:
        detail = traceback.format_exc()
        _mark_failed(db_path, game_id, f"{exc}\n{detail[-400:]}")
        print(detail, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
