"""Tests for SQLite connection configuration."""


def test_open_sqlite_connection_sets_wal_and_busy_timeout(tmp_path):
    from helpers import open_sqlite_connection

    db_path = tmp_path / "busy.db"
    conn = open_sqlite_connection(str(db_path), row_factory=None)
    try:
        journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
        busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert journal.lower() == "wal"
        assert int(busy) >= 60000
    finally:
        conn.close()
