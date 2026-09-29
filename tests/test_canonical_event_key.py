"""The stat page reads one event copy. The newest finished run wins."""

import sqlite3

from program_mode import canonical_event_key


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE analysis_runs (
            id INTEGER PRIMARY KEY,
            analysis_key TEXT,
            status TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE events (
            id INTEGER PRIMARY KEY,
            game_id TEXT,
            review_status TEXT
        )"""
    )
    return conn


def _event(conn, game_id, n, status="accepted"):
    for _ in range(n):
        conn.execute(
            "INSERT INTO events (game_id, review_status) VALUES (?, ?)",
            (game_id, status),
        )


def test_newest_finished_run_beats_an_older_denser_copy():
    conn = _db()
    base = "jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334"
    older = base + "__rerun_20260915_193718"
    newest = base + "__rerun_20260928_031027"
    conn.execute("INSERT INTO analysis_runs (id, analysis_key, status) VALUES (1, ?, 'completed')", (base,))
    conn.execute("INSERT INTO analysis_runs (id, analysis_key, status) VALUES (2, ?, 'failed')", (older,))
    conn.execute("INSERT INTO analysis_runs (id, analysis_key, status) VALUES (9, ?, 'completed')", (newest,))
    _event(conn, base, 10)
    _event(conn, older, 50)
    _event(conn, newest, 20)
    assert canonical_event_key(conn, base) == newest
    assert canonical_event_key(conn, newest) == newest


def test_densest_copy_wins_when_nothing_has_finished():
    conn = _db()
    base = "game"
    older = base + "__rerun_old"
    conn.execute("INSERT INTO analysis_runs (id, analysis_key, status) VALUES (1, ?, 'failed')", (base,))
    conn.execute("INSERT INTO analysis_runs (id, analysis_key, status) VALUES (2, ?, 'failed')", (older,))
    _event(conn, base, 3)
    _event(conn, older, 9)
    assert canonical_event_key(conn, base) == older
