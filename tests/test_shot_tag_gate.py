"""The count gate: right / makes missed / misses called makes on the coach's shot tags.

These tests need no film, no database and no OpenCV, so they run in CI. They pin the
three things that have gone wrong before: the scoring arithmetic, the 8 second match
tolerance drifting away from the teach pass, and a taught row being counted as the
program's own work.
"""

import json
from pathlib import Path

import pytest

import shot_tag_gate as gate

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "benchmarks" / "shot_tags" / "baseline.json"
ADRIAN_Q1_TAGS = ROOT / "tag-exports" / "jrhigh_adrian_q1_manual_tags.json"
ADRIAN_Q1_TRUTH = ROOT / "benchmarks" / "accuracy" / "adrian_q1" / "truth.json"


def _tag(ms, made, kind="2PT"):
    return {"ms": ms, "made": made, "kind": kind, "label": f"{kind} {ms}"}


def _make(ms):
    return {"event_type": "made_two", "timestamp_ms": ms}


# --- the arithmetic ---------------------------------------------------------------

def test_the_three_buckets_always_sum_to_the_tag_count():
    tags = [_tag(1000, True), _tag(30000, False), _tag(60000, True)]
    for makes in ([], [_make(1000)], [_make(30000)], [_make(1000), _make(30000), _make(60000)]):
        result = gate.score(tags, gate.stored_makes(makes))
        assert result["right"] + result["makes_missed"] + result["misses_called_makes"] == 3


def test_calling_every_shot_a_miss_scores_the_misses_and_nothing_else():
    """The published sanity check: 111 tags, 38 makes, so a do-nothing run scores 73."""
    tags = [_tag(i * 20000, i < 38) for i in range(111)]
    result = gate.score(tags, [])
    assert (result["right"], result["makes_missed"], result["misses_called_makes"]) == (73, 38, 0)


def test_a_run_that_finds_every_make_and_invents_none_scores_everything():
    tags = [_tag(i * 20000, i % 3 == 0) for i in range(30)]
    makes = gate.stored_makes([_make(t["ms"]) for t in tags if t["made"]])
    result = gate.score(tags, makes)
    assert result["right"] == 30
    assert result["makes_missed"] == result["misses_called_makes"] == 0


def test_calling_every_shot_a_make_turns_every_tagged_miss_into_a_false_make():
    tags = [_tag(i * 20000, i < 4) for i in range(10)]
    result = gate.score(tags, gate.stored_makes([_make(t["ms"]) for t in tags]))
    assert (result["right"], result["makes_missed"], result["misses_called_makes"]) == (4, 0, 6)


# --- the match rule --------------------------------------------------------------

def test_the_tolerance_is_the_same_8_seconds_the_teach_pass_uses():
    """If manual_tag_teach moves, this gate has to move with it or stop meaning anything."""
    from manual_tag_teach import MATCH_TOLERANCE_MS

    assert gate.MATCH_TOLERANCE_MS == MATCH_TOLERANCE_MS == 8000


def test_the_clock_parser_agrees_with_the_teach_pass():
    from manual_tag_teach import time_to_ms as production

    for value in ("0:02.0", "2:31.6", "16:00.7", "151.6", "", None, "garbage", "12"):
        assert gate.time_to_ms(value) == production(value), value


def test_a_make_just_inside_the_tolerance_counts_and_just_outside_does_not():
    tag = [_tag(100000, True)]
    assert gate.score(tag, [{"ms": 107999}])["right"] == 1
    assert gate.score(tag, [{"ms": 108001}])["makes_missed"] == 1


def test_one_stored_make_cannot_grade_two_tags():
    """Otherwise a single row near a cluster answers for all of them."""
    result = gate.score([_tag(100000, True), _tag(101000, True)], [{"ms": 100500}])
    assert (result["right"], result["makes_missed"]) == (1, 1)


def test_a_correct_row_is_not_scored_twice_as_wrong():
    """A tagged miss next door must not swallow the make that belongs to a tagged make.

    Walking the tags in time order used to do exactly that: the miss at 100.0 s took
    the row, so the make at 101.0 s read as a missed make *and* the miss read as a
    miss called a make -- two errors invented out of one right answer.
    """
    result = gate.score([_tag(100000, False), _tag(101000, True)], [{"ms": 101000}])
    assert result["right"] == 2
    assert result["makes_missed"] == result["misses_called_makes"] == 0


# --- what counts as the program's own claim --------------------------------------

def test_a_rejected_row_is_not_a_make():
    rejected = [{"event_type": "made_two", "timestamp_ms": 1000, "review_status": "rejected"}]
    assert gate.stored_makes(rejected) == []


def test_the_coachs_own_tag_written_as_a_row_cannot_grade_itself():
    manual = [{"event_type": "made_two", "timestamp_ms": 1000, "source_type": "manual"}]
    assert gate.stored_makes(manual) == []


def test_a_row_the_teach_pass_corrected_from_a_tag_is_not_the_programs_work():
    taught = [{"event_type": "made_two", "timestamp_ms": 1000, "review_status": "corrected"}]
    assert gate.stored_makes(taught) == []
    assert len(gate.stored_makes(taught, count_taught=True)) == 1


def test_pending_and_accepted_rows_do_count():
    rows = [{"event_type": "made_three", "timestamp_ms": 1000, "review_status": "pending"},
            {"event_type": "made_free_throw", "timestamp_ms": 2000, "review_status": "accepted"}]
    assert len(gate.stored_makes(rows)) == 2


def test_a_missed_shot_row_is_never_a_make():
    rows = [{"event_type": "missed_two", "timestamp_ms": 1000},
            {"event_type": "shot", "timestamp_ms": 2000, "shot_result": "miss"}]
    assert gate.stored_makes(rows) == []


def test_a_generic_shot_row_is_read_from_its_result():
    rows = [{"event_type": "shot", "timestamp_ms": 2000, "shot_result": "make"}]
    assert len(gate.stored_makes(rows)) == 1


# --- the floor -------------------------------------------------------------------

def test_every_recorded_floor_is_internally_consistent():
    floors = json.loads(BASELINE.read_text(encoding="utf-8"))
    checked = 0
    for name, floor in floors.items():
        if name.startswith("_"):
            continue
        total = floor["right"] + floor["makes_missed"] + floor["misses_called_makes"]
        assert total == floor["tags"], f"{name}: {total} != {floor['tags']} tags"
        checked += 1
    assert checked, "no floors to check"


def test_the_adrian_floor_is_the_score_the_handoffs_recorded():
    floor = json.loads(BASELINE.read_text(encoding="utf-8"))["adrian_111"]
    assert (floor["tags"], floor["right"], floor["makes_missed"],
            floor["misses_called_makes"]) == (111, 85, 20, 6)


def test_a_score_at_the_floor_passes_and_one_right_answer_less_fails():
    floor = {"tags": 111, "right": 85, "makes_missed": 20, "misses_called_makes": 6}
    assert gate.regressions({**floor}, floor) == []
    worse = {"tags": 111, "right": 84, "makes_missed": 21, "misses_called_makes": 6}
    assert gate.regressions(worse, floor)


def test_trading_a_missed_make_for_a_false_make_is_not_a_pass():
    """Same total, worse card: a miss called a make puts points on it that never happened."""
    floor = {"tags": 111, "right": 85, "makes_missed": 20, "misses_called_makes": 6}
    traded = {"tags": 111, "right": 85, "makes_missed": 19, "misses_called_makes": 7}
    assert gate.regressions(traded, floor)


def test_a_score_on_a_different_answer_key_is_refused_rather_than_compared():
    floor = {"tags": 111, "right": 85, "makes_missed": 20, "misses_called_makes": 6}
    shorter = {"tags": 44, "right": 85, "makes_missed": 20, "misses_called_makes": 6}
    problems = gate.regressions(shorter, floor)
    assert problems and "not comparable" in problems[0]


def test_the_summary_line_names_all_three_numbers():
    line = gate.summary_line({"right": 85, "makes_missed": 20,
                              "misses_called_makes": 6, "tags": 111})
    for part in ("right=85", "makes_missed=20", "misses_called_makes=6", "111"):
        assert part in line


# --- the committed Adrian Q1 answer key ------------------------------------------

def test_the_committed_adrian_q1_tags_hold_44_shot_tags():
    """The teach calibrator carries 44 shot anchors for Q1; the tags have to match."""
    export = json.loads(ADRIAN_Q1_TAGS.read_text(encoding="utf-8"))
    tags = gate.shot_tags(export["rows"])
    assert len(tags) == 44
    assert sum(1 for t in tags if t["made"]) == 15


def test_the_adrian_q1_benchmark_fixture_matches_the_tag_export():
    """truth.json is generated. If it drifts from the export, it was hand-edited."""
    export = json.loads(ADRIAN_Q1_TAGS.read_text(encoding="utf-8"))
    truth = json.loads(ADRIAN_Q1_TRUTH.read_text(encoding="utf-8"))
    assert gate.shot_tags(truth["rows"]) == gate.shot_tags(export["rows"])
    assert truth["window_sec"] == 961


def test_the_benchmark_fixture_carries_no_roster():
    """Fixtures travel with the repo, so no player names or notes in them."""
    truth = json.loads(ADRIAN_Q1_TRUTH.read_text(encoding="utf-8"))
    for row in truth["rows"]:
        assert "player" not in row and "notes" not in row


# --- the real answer key, when the machine running this has it -------------------

def test_the_full_111_tag_gate_still_holds():
    """Hard-fails if the run scores below the floor. Skips where the data is not.

    This is the only test that scores the real film. CI has neither the database nor
    the tags, so it skips there and says why. On the home laptop, or on a clone with
    the Shared drive folder copied over it, it runs for real.
    """
    db = ROOT / "film_analysis.db"
    if not db.is_file():
        pytest.skip("film_analysis.db is not here; the count gate only runs where the data is")
    tag_dir = ROOT / "data" / "film_tags"
    tag_files = [p for p in tag_dir.glob("*.json") if "adrian" in p.name.lower()]
    if not tag_files:
        pytest.skip("no Adrian tag file in data/film_tags/; copy the Shared drive folder over")

    import sqlite3

    floor = json.loads(BASELINE.read_text(encoding="utf-8"))["adrian_111"]
    export = json.loads(tag_files[0].read_text(encoding="utf-8"))
    tags = gate.shot_tags(export.get("rows") or [])
    if len(tags) != floor["tags"]:
        pytest.skip(f"{tag_files[0].name} holds {len(tags)} shot tags, not {floor['tags']}; "
                    "score it with scripts/shot_tag_score.py and set the floor there")

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        keys = [r[0] for r in conn.execute(
            "SELECT DISTINCT game_id FROM events WHERE game_id LIKE '%adrian%'")]
        runs = sorted(k for k in keys if "__rerun_" in k) or keys
        if not runs:
            pytest.skip("no Adrian run in the events table")
        events = [dict(r) for r in conn.execute(
            "SELECT id, event_type, shot_result, timestamp_ms, review_status, source_type "
            "FROM events WHERE game_id = ?", (runs[-1],))]
    finally:
        conn.close()

    result = gate.score(tags, gate.stored_makes(events))
    problems = gate.regressions(result, floor)
    assert not problems, (f"{runs[-1]}: {gate.summary_line(result)}\n" + "\n".join(problems))
