import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import migrate_paths as mp  # noqa: E402

WIN = r"C:\Users\scott\Documents\liberty-basketball-analysis\uploads"


def _db(path: Path):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE videos (id INTEGER PRIMARY KEY, file_path TEXT);
        CREATE TABLE analysis_runs (id INTEGER PRIMARY KEY, video_path TEXT);
        CREATE TABLE play_steps (id INTEGER PRIMARY KEY, source_image TEXT);
    """)
    conn.executemany("INSERT INTO videos (file_path) VALUES (?)", [
        (WIN + r"\game1.mp4",), (r"c:/users/scott/documents/liberty-basketball-analysis/uploads/sub/game2.mp4",),
        ("/already/posix/game3.mp4",), (None,),
    ])
    conn.execute("INSERT INTO analysis_runs (video_path) VALUES (?)", (WIN + r"\game1.mp4",))
    conn.execute("INSERT INTO play_steps (source_image) VALUES (?)", ("uploads/play_imports/p.png",))
    conn.commit()
    return conn


def test_rewrite_value_handles_case_and_separators():
    assert mp.rewrite_value(WIN + r"\a\b.mp4", WIN, "/x/uploads") == "/x/uploads/a/b.mp4"
    assert mp.rewrite_value("C:/USERS/scott/Documents/liberty-basketball-analysis/uploads/a.mp4", WIN, "/x") == "/x/a.mp4"
    assert mp.rewrite_value("/other/a.mp4", WIN, "/x") is None
    assert mp.rewrite_value("", WIN, "/x") is None


def test_audit_counts_windows_paths(tmp_path):
    conn = _db(tmp_path / "t.db")
    report = mp.audit(conn)
    assert report["videos.file_path"]["windows_style"] == 2
    assert report["analysis_runs.video_path"]["windows_style"] == 1
    assert "play_steps.source_image" in report


def test_dry_run_changes_nothing_and_apply_rewrites(tmp_path):
    conn = _db(tmp_path / "t.db")
    dry = mp.rewrite_db(conn, WIN, "/home/me/LibertyData/uploads", apply=False)
    assert dry["videos.file_path"] == 2 and dry["analysis_runs.video_path"] == 1
    assert conn.execute("SELECT file_path FROM videos WHERE id=1").fetchone()[0].startswith("C:")
    mp.rewrite_db(conn, WIN, "/home/me/LibertyData/uploads", apply=True)
    rows = [r[0] for r in conn.execute("SELECT file_path FROM videos ORDER BY id")]
    assert rows[0] == "/home/me/LibertyData/uploads/game1.mp4"
    assert rows[1] == "/home/me/LibertyData/uploads/sub/game2.mp4"
    assert rows[2] == "/already/posix/game3.mp4" and rows[3] is None
    assert mp.audit(conn)["videos.file_path"]["windows_style"] == 0


def test_stat_book_drafts(tmp_path):
    d = tmp_path / "stat_books" / "g1"; d.mkdir(parents=True)
    (d / "draft.json").write_text(json.dumps({"box": {}, "meta": {"aligned_image": WIN + r"\stat_books\g1\aligned.png", "ocr": {"backend": "none"}}}))
    assert mp.rewrite_stat_book_drafts(tmp_path / "stat_books", WIN, "/new/uploads", apply=False) == 1
    assert "C:" in (d / "draft.json").read_text()
    mp.rewrite_stat_book_drafts(tmp_path / "stat_books", WIN, "/new/uploads", apply=True)
    assert json.loads((d / "draft.json").read_text())["meta"]["aligned_image"] == "/new/uploads/stat_books/g1/aligned.png"


def test_cli_dry_run(tmp_path, capsys):
    _db(tmp_path / "t.db").close()
    rc = mp.main(["--db", str(tmp_path / "t.db"), "--from-prefix", WIN, "--to-prefix", "/n"])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"mode": "DRY RUN"' in out
