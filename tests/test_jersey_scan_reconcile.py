"""Tests for stuck jersey OCR scan reconciliation."""


def test_reconcile_stuck_jersey_scan_clears_legacy_running(db):
    from helpers import reconcile_stuck_jersey_scan

    db.execute("INSERT INTO games (source_type, source_key) VALUES ('manual', 'jersey-stuck')")
    game_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    analysis_key = "nfhs_jersey_stuck"
    db.execute(
        """INSERT INTO analysis_runs (analysis_key, game_id, video_path, status, progress_step)
           VALUES (?, ?, ?, 'completed', 'jersey_scan:running')""",
        (analysis_key, game_id, "/tmp/stuck.mp4"),
    )
    db.commit()

    assert reconcile_stuck_jersey_scan(db, analysis_key) is True
    row = db.execute(
        "SELECT progress_step FROM analysis_runs WHERE analysis_key=?",
        (analysis_key,),
    ).fetchone()
    assert str(row["progress_step"]).startswith("jersey_scan:failed:")


def test_reconcile_stuck_jersey_scan_ignores_recent_scan(db, monkeypatch):
    import time
    from helpers import jersey_scan_running_step, reconcile_stuck_jersey_scan

    db.execute("INSERT INTO games (source_type, source_key) VALUES ('manual', 'jersey-fresh')")
    game_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    analysis_key = "nfhs_jersey_fresh"
    db.execute(
        """INSERT INTO analysis_runs (analysis_key, game_id, video_path, status, progress_step)
           VALUES (?, ?, ?, 'completed', ?)""",
        (analysis_key, game_id, "/tmp/fresh.mp4", jersey_scan_running_step()),
    )
    db.commit()

    assert reconcile_stuck_jersey_scan(db, analysis_key) is False


def test_reconcile_stuck_jersey_scan_times_out_old_scan(db, monkeypatch):
    from helpers import reconcile_stuck_jersey_scan

    db.execute("INSERT INTO games (source_type, source_key) VALUES ('manual', 'jersey-old')")
    game_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    analysis_key = "nfhs_jersey_old"
    old_started = 1_600_000_000
    db.execute(
        """INSERT INTO analysis_runs (analysis_key, game_id, video_path, status, progress_step)
           VALUES (?, ?, ?, 'completed', ?)""",
        (analysis_key, game_id, "/tmp/old.mp4", f"jersey_scan:running:{old_started}"),
    )
    db.commit()

    assert reconcile_stuck_jersey_scan(db, analysis_key, max_age_seconds=60) is True
