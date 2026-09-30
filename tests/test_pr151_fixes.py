"""Regression tests for the fixes stacked on PR #151 (docs/validation/pr151_fixes.md).

Regressions against main that already have tests (and failed on 5b7c2a3):
  tests/e2e/test_journey_film.py::test_rerun_labels_second_run_keeps_primary_and_compare_lists_both
  tests/e2e/test_e2e_flow.py::test_09_review_ledger_highlights_clips_playlists
  tests/test_playbook_sheet_align.py::test_playbook_html_has_align_ready_banner
"""
from __future__ import annotations

import numpy as np
import pytest

# ── canonical_event_key: a new unreviewed rerun must not hide the coach's work ─


def _run(db, key, base, kind):
    db.execute(
        """INSERT INTO analysis_runs (analysis_key, base_analysis_key, video_path, status, run_kind)
           VALUES (?, ?, '/nonexistent.mp4', 'completed', ?)""",
        (key, base, kind),
    )


def _events(db, key, status, n):
    for i in range(n):
        db.execute(
            """INSERT INTO events (game_id, event_type, timestamp_ms, source_type, review_status)
               VALUES (?, 'made_two', ?, 'ai', ?)""",
            (key, i * 1000, status),
        )


@pytest.mark.parametrize(
    "base_status,rerun_status,expected",
    [
        ("accepted", "pending", "base"),    # coach reviewed the older copy: keep it
        ("corrected", "pending", "base"),
        ("pending", "pending", "rerun"),    # nobody reviewed anything: newest run (PR #151 rule)
        ("accepted", "accepted", "rerun"),  # both reviewed: newest run
    ],
)
def test_canonical_key_keeps_the_coach_reviewed_run(app, db, base_status, rerun_status, expected):
    from program_mode import canonical_event_key

    base = "vid_game_1"
    rerun = base + "__rerun_20260929_120000"
    _run(db, base, base, "primary")
    _run(db, rerun, base, "rerun")
    _events(db, base, base_status, 5)
    _events(db, rerun, rerun_status, 8)
    db.commit()
    want = base if expected == "base" else rerun
    assert canonical_event_key(db, base) == want
    assert canonical_event_key(db, rerun) == want


# ── AI line score was 0-0 for every game without a scoreboard track ──────────


def test_ai_line_score_uses_video_quarters_without_a_scoreboard_track(app, db, monkeypatch):
    import game_boxscore
    from game_boxscore import build_official_box

    # A confirmed book with player lines but no Q1-Q4 cells: the line score comes
    # from the AI events, and this game has no scoreboard track.
    book = {"home_team": "Liberty", "away_team": "Vale",
            "players": [{"jersey": "5", "name": "Avery", "team": "home"}]}
    monkeypatch.setattr(game_boxscore, "load_scorebook", lambda _gid: book)
    key = "no_scoreboard_game"
    _run(db, key, key, "primary")
    # 4 made twos spread through a 40-minute film (one per quarter by time)
    for i, ts in enumerate((60_000, 660_000, 1_260_000, 1_860_000)):
        db.execute(
            """INSERT INTO events (game_id, player, event_type, shot_result, timestamp_ms, source_type,
                                   review_status, details_json)
               VALUES (?, '5', 'made_two', 'made', ?, 'ai', 'pending', '{"team_side": "home", "jersey_number": "5"}')""",
            (key, ts),
        )
    db.commit()
    box = build_official_box(db, key, event_counts=True)
    quarters = [row for row in box["line_score"] if str(row.get("period", "")).startswith("Q")]
    liberty_by_quarter = sum(int(row.get("liberty") or 0) for row in quarters)
    assert box["line_score_source"] != "scorebook"
    assert liberty_by_quarter == 8, box["line_score"]
    assert [int(r["liberty"]) for r in quarters] == [2, 2, 2, 2]


# ── A scoreboard clock with an unreadable digit is not a clock ───────────────


def test_unreadable_clock_digit_does_not_make_a_legal_clock(monkeypatch):
    import scoreboard_clock as sc

    # four glyph blocks, 4 px apart (one group), each dense enough to read
    mask = np.zeros((20, 40), dtype=np.uint8)
    for x0 in (2, 12, 22, 32):
        mask[2:18, x0:x0 + 6] = 1
    reads = iter(["1", "0", None, "9"])  # the third glyph has no template
    monkeypatch.setattr(sc, "_segment_digit", lambda piece: next(reads))
    groups = sc._digit_groups(mask)
    assert sc._clock_text(groups) is None, groups
    assert not sc.legal_clock(sc._clock_text(groups))
    assert sc.quarter_from_scoreboard({"clock": sc._clock_text(groups), "period": "2"}) is None


def test_fully_read_clock_still_works():
    import scoreboard_clock as sc

    assert sc._clock_text(["10", "59"]) == "10:59"
    assert sc._clock_text(["7", "49"]) == "7:49"
    assert sc.legal_clock("7:49")


# ── ai_bridge tracker matching crashed with NameError ────────────────────────


def test_ai_bridge_tracks_more_than_one_person():
    pytest.importorskip("cv2")
    from ai_bridge import BasketballStatsAdapter, DetectionData

    adapter = BasketballStatsAdapter()
    dets = [
        DetectionData(frame_number=10, timestamp_ms=333.0, object_class="person", confidence=0.9,
                      x_center=100.0, y_center=200.0, width=40.0, height=90.0),
        DetectionData(frame_number=10, timestamp_ms=333.0, object_class="person", confidence=0.9,
                      x_center=400.0, y_center=210.0, width=40.0, height=90.0),
        DetectionData(frame_number=11, timestamp_ms=366.0, object_class="person", confidence=0.9,
                      x_center=102.0, y_center=201.0, width=40.0, height=90.0),
    ]
    out = adapter.synchronize_tracker_ids(dets)
    assert len(out) == 3
    ids = [t.tracker_id for t in out]
    assert ids[0] != ids[1]          # two different players
    assert ids[2] == ids[0]          # the first player a frame later keeps his id


def test_ai_bridge_core_make_functions_import():
    pytest.importorskip("cv2")
    import ai_bridge

    assert ai_bridge.ball_through_rim is not None
    assert ai_bridge.net_moved_after_shot is not None
