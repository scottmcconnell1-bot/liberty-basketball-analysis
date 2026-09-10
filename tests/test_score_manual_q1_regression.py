"""The manual-vs-AI Q1 scorer must work from a DB that never had film_tool_games."""

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tag-exports"))

BACKUP = ROOT / "tag-exports" / "liberty-manual-tags-backup.json"
pytestmark = pytest.mark.skipif(not BACKUP.is_file(), reason="manual Q1 tag backup not present")


def _db_with_events(path: Path, rows):
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE events (id INTEGER PRIMARY KEY, game_id TEXT, event_type TEXT,
           shot_result TEXT, timestamp_ms INTEGER, details_json TEXT, source_type TEXT,
           player TEXT)"""
    )
    conn.executemany(
        "INSERT INTO events (game_id, event_type, shot_result, timestamp_ms, details_json, source_type, player) VALUES (?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()


def test_load_manual_rows_falls_back_to_backup_without_table(tmp_path):
    import score_manual_q1_regression as scorer

    db = tmp_path / "bare.db"
    sqlite3.connect(db).close()  # exists, but no film_tool_games table
    rows, liberty = scorer.load_manual_rows(db)
    assert liberty == "Liberty"
    assert len(rows) > 50


def test_window_restricts_manual_and_ai_and_scores_a_planted_match(tmp_path):
    import score_manual_q1_regression as scorer

    # The first manual action tag in the backup is a 3PT miss at 0:34.3; plant one AI
    # 3PT miss 1 s later and nothing else. Expect exactly one exact match in a 60 s window.
    db = tmp_path / "t.db"
    _db_with_events(db, [
        ("k", "shot", "miss", 35300, json.dumps({"shot_type": "3pt"}), "ai", "1"),
        ("k", "shot", "make", 800000, json.dumps({"shot_type": "2pt"}), "ai", "2"),  # outside window
    ])
    result = scorer.score("k", db, window_end_sec=60)
    assert result["window_end_sec"] == 60
    assert result["ai_comparable_events"] == 1
    assert result["exact_matches"] == 1
    assert result["per_type"]["3PT"]["matched"] == 1
    assert result["per_tag"][0]["verdict"] == "MATCH"
    assert result["manual_action_tags"] < scorer.score("k", db)["manual_action_tags"]


def test_cli_runs_with_window(tmp_path, capsys):
    import score_manual_q1_regression as scorer

    db = tmp_path / "empty.db"
    _db_with_events(db, [])
    rc = scorer.main(["--analysis-key", "none", "--db", str(db), "--window-end-sec", "300", "--no-fail", "--per-tag"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["exact_matches"] == 0 and out["ai_only"] == 0
