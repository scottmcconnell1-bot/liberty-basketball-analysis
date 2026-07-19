"""Regression gate for AI event precision vs manual Q1 ground truth.

Skips when the Wilder Q1 analysis run / film_tool tags are not present locally.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "film_analysis.db"
ANALYSIS_KEY = (
    "nfhs_gam30b09cbb4f_20260706_173156_trim_20260706_180340_"
    "trim_20260706_185339_trim_20260706_191311__rerun_20260718_215754"
)


def _q1_assets_available() -> bool:
    if not DB_PATH.exists():
        return False
    conn = sqlite3.connect(str(DB_PATH))
    try:
        events = conn.execute(
            "SELECT COUNT(*) FROM events WHERE game_id=?",
            (ANALYSIS_KEY,),
        ).fetchone()[0]
        tags = conn.execute(
            "SELECT COUNT(*) FROM film_tool_games WHERE client_game_id=?",
            ("game-1784304093435",),
        ).fetchone()[0]
    except sqlite3.Error:
        return False
    finally:
        conn.close()
    return events > 0 and tags > 0


@pytest.mark.skipif(not _q1_assets_available(), reason="Local Q1 analysis + film-tool tags required")
def test_manual_q1_regression_gates():
    import sys

    sys.path.insert(0, str(ROOT / "tag-exports"))
    from score_manual_q1_regression import evaluate_gates, score

    result = score(ANALYSIS_KEY, DB_PATH)
    failures = evaluate_gates(result)
    assert not failures, f"Q1 regression failed: {failures}; score={result}"
