"""End-to-end coach journeys for STATS, EVENT REVIEW, BOX SCORE and SCOREBOOK.

Every journey drives the app through the HTTP routes a coach's browser uses
(save_event from the Film Tool, the /api/review/events/* review buttons, the
/stat-books review/confirm screen, the program summary / official box) and
asserts exact numbers computed by hand in the test.

Tests that expose real defects keep asserting the CORRECT behaviour and are
marked ``xfail(strict=True, reason="BUG: ...")`` so they flip to XPASS (and
fail the run) once the bug is fixed.

Isolation: function-scoped ``app``/``client`` fixtures from tests/conftest.py
(temp SQLite DB + temp UPLOAD_FOLDER); confirmed scorebooks go to the
conftest's temp CONFIRMED_ROOT. No CV, network or subprocesses are used.
"""
from __future__ import annotations

import io
import json
import os
import sqlite3
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

JSON = "application/json"


# ── helpers ─────────────────────────────────────────────────────────────────

def _post(client, path, payload):
    return client.post(path, data=json.dumps(payload), content_type=JSON)


def _put(client, path, payload):
    return client.put(path, data=json.dumps(payload), content_type=JSON)


def _ok(resp, *codes):
    codes = codes or (200,)
    assert resp.status_code in codes, f"{resp.status_code} not in {codes}: {resp.data[:400]!r}"
    return resp.get_json()


def _conn(app) -> sqlite3.Connection:
    conn = sqlite3.connect(app.config["DATABASE"], timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _query(app, sql, params=()):
    conn = _conn(app)
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _create_game(client, key="journey-game") -> int:
    body = _ok(_post(client, "/api/games", {"source_type": "manual", "source_key": key}), 201)
    return int(body["id"])


def _create_roster(client, players):
    ids = {}
    for jersey, name in players:
        body = _ok(_post(client, "/api/players", {"name": name, "jersey_number": int(jersey)}), 201)
        ids[name] = body["id"]
    return ids


def _tag(client, game_id, event_type, player, ts, shot_result=None, **extra):
    """One Film Tool manual tag (human_verified defaults to True -> accepted)."""
    payload = {"game_id": game_id, "event_type": event_type, "player": player, "timestamp_ms": ts}
    if shot_result is not None:
        payload["shot_result"] = shot_result
    payload.update(extra)
    body = _ok(_post(client, "/api/save_event", payload))
    assert body["status"] == "success"
    return body["id"]


def _event_type_id(conn, code):
    row = conn.execute("SELECT id FROM event_types WHERE code=?", (code,)).fetchone()
    return row["id"] if row else None


def _insert_ai_draft(app, game_id, event_type, player, ts, shot_result=None, confidence=0.6,
                     relational=True, details=None):
    """An AI draft exactly as event_generator.persist_events stores it (pending, source 'ai')."""
    conn = _conn(app)
    try:
        cur = conn.execute(
            """INSERT INTO events (game_id, relational_game_id, player, event_type, event_type_id,
                                   shot_result, timestamp_ms, details_json, confidence, source_type)
               VALUES (?,?,?,?,?,?,?,?,?, 'ai')""",
            (str(game_id), int(game_id) if relational else None, player, event_type,
             _event_type_id(conn, event_type), shot_result, ts, json.dumps(details or {}), confidence),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _stats_by_player(client, game_key):
    body = _ok(client.get(f"/api/stats/{game_key}"))
    return {row["player"]: row for row in body["basic"]}, body


STAT_KEYS = ("pts", "fgm", "fga", "threes_made", "threes_att", "ast", "reb", "tov", "stl", "blk")


def _line(**kw):
    out = {k: 0 for k in STAT_KEYS}
    out.update(kw)
    return out


def _pick(row, keys=STAT_KEYS):
    return {k: row[k] for k in keys}


@pytest.fixture
def program_books(monkeypatch):
    """program_mode.load_scorebook reads <repo>/data/stat_books/confirmed directly; point it at
    the same (temp) CONFIRMED_ROOT the /stat-books confirm route writes to, as in production
    where both resolve to the same directory."""
    import program_mode
    from stat_book import paths as sb_paths

    monkeypatch.setattr(program_mode, "scorebook_path",
                        lambda gid: sb_paths.CONFIRMED_ROOT / f"{gid.strip()}.json")
    return sb_paths


# ── Journey 1: manual tagging -> per-player + team stats ─────────────────────

ROSTER = [("1", "Avery Northwind"), ("3", "Blake Ironwood"), ("5", "Casey Riverbend")]
AVERY, BLAKE, CASEY = (n for _, n in ROSTER)


def _tag_journey_one(client, gid, made_result="made"):
    """A realistic first half. Returns nothing; expected totals are hand-computed below."""
    t = iter(range(1_000, 200_000, 1_000))
    # Avery: 2x made 2, missed 2, made 3, missed 3, 2 FTM, 1 FT miss, 1 AST, 1 TO
    _tag(client, gid, "made_two", AVERY, next(t), made_result)
    _tag(client, gid, "made_two", AVERY, next(t), made_result)
    _tag(client, gid, "missed_two", AVERY, next(t), "missed")
    _tag(client, gid, "made_three", AVERY, next(t), made_result)
    _tag(client, gid, "missed_three", AVERY, next(t), "missed")
    _tag(client, gid, "made_free_throw", AVERY, next(t), made_result)
    _tag(client, gid, "made_free_throw", AVERY, next(t), made_result)
    _tag(client, gid, "missed_free_throw", AVERY, next(t), "missed")
    _tag(client, gid, "assist", AVERY, next(t))
    _tag(client, gid, "turnover", AVERY, next(t))
    # Blake: 2 DREB, 1 OREB, 2 STL, made 2, 2 AST
    _tag(client, gid, "rebound_defensive", BLAKE, next(t))
    _tag(client, gid, "rebound_defensive", BLAKE, next(t))
    _tag(client, gid, "rebound_offensive", BLAKE, next(t))
    _tag(client, gid, "steal", BLAKE, next(t))
    _tag(client, gid, "steal", BLAKE, next(t))
    _tag(client, gid, "made_two", BLAKE, next(t), made_result)
    _tag(client, gid, "assist", BLAKE, next(t))
    _tag(client, gid, "assist", BLAKE, next(t))
    # Casey: made 3, block, turnover
    _tag(client, gid, "made_three", CASEY, next(t), made_result)
    _tag(client, gid, "block", CASEY, next(t))
    _tag(client, gid, "turnover", CASEY, next(t))


# Hand-computed. FG columns are field goals only (free throws are not field goals).
J1_EXPECTED = {
    AVERY: _line(pts=2 + 2 + 3 + 1 + 1, fgm=3, fga=5, threes_made=1, threes_att=2, ast=1, tov=1),
    BLAKE: _line(pts=2, fgm=1, fga=1, reb=3, stl=2, ast=2),
    CASEY: _line(pts=3, fgm=1, fga=1, threes_made=1, threes_att=1, blk=1, tov=1),
}
NON_FG_KEYS = ("pts", "threes_made", "threes_att", "ast", "reb", "tov", "stl", "blk")


def test_journey_manual_tagging_player_and_team_stats(app, client):
    gid = _create_game(client, "j1-manual")
    _create_roster(client, ROSTER)
    _tag_journey_one(client, gid)

    # every tag landed as a coach-trusted manual event on the relational game
    rows = _query(app, "SELECT review_status, source_type, relational_game_id, event_type_id FROM events")
    assert len(rows) == 21
    assert {r["review_status"] for r in rows} == {"accepted"}
    assert {r["source_type"] for r in rows} == {"manual"}
    assert {r["relational_game_id"] for r in rows} == {gid}
    assert all(r["event_type_id"] is not None for r in rows)

    by_player, body = _stats_by_player(client, gid)
    assert set(by_player) == {AVERY, BLAKE, CASEY}
    for name, exp in J1_EXPECTED.items():
        assert _pick(by_player[name], NON_FG_KEYS) == _pick(exp, NON_FG_KEYS), name
    # every line exact, incl. FG columns (Avery's 3 free throws stay out of FGM/FGA)
    for name in (AVERY, BLAKE, CASEY):
        assert _pick(by_player[name]) == J1_EXPECTED[name], name
    assert sum(r["pts"] for r in by_player.values()) == 9 + 2 + 3
    assert body["enhanced"]["basic_stats"] == body["basic"]

    # persisted stats table (rebuilt by save_event -> refresh_game_stats) matches the API
    persisted = {r["player_name"]: r for r in _query(
        app, "SELECT * FROM stats WHERE relational_game_id=?", (gid,))}
    assert set(persisted) == {AVERY, BLAKE, CASEY}
    for name in (AVERY, BLAKE, CASEY):
        assert _pick(persisted[name]) == _pick(by_player[name]), name
        assert persisted[name]["game_id"] == str(gid)

    # team four factors, hand-computed:
    #   FGA 7, FGM 5, 3PM 2, FTA 3, TOV 2, ORB 1, DRB 2
    ff = _ok(client.get(f"/api/four_factors/{gid}"))
    assert ff == {
        "efg_pct": round((5 + 0.5 * 2) / 7, 4),
        "tov_pct": round(2 / (7 + 0.44 * 3 + 2), 4),
        "orb_pct": round(1 / 3, 4),
        "ft_rate": round(3 / 7, 4),
    }

    # official box (no scorebook yet): every film line is unassigned but exact, incl. FTs
    summary = _ok(client.get(f"/api/program/{gid}/summary"))
    assert summary["counts"] == {"pending": 0, "accepted": 21, "corrected": 0, "rejected": 0}
    box = summary["official_box"]
    assert box is not None and box["scorebook_present"] is False
    assert box["line_score_source"] == "ai_video_split"
    unassigned = {r["jersey"]: r for r in box["unassigned"]}
    avery = unassigned[AVERY]
    assert (avery["pts"], avery["fgm"], avery["fga"], avery["fgm3"], avery["fga3"],
            avery["ftm"], avery["fta"], avery["ast"], avery["tov"]) == (9, 3, 5, 1, 2, 2, 3, 1, 1)
    blake = unassigned[BLAKE]
    assert (blake["pts"], blake["oreb"], blake["dreb"], blake["reb"], blake["stl"], blake["ast"]) == (2, 1, 2, 3, 2, 2)
    assert unassigned[CASEY]["pts"] == 3 and unassigned[CASEY]["blk"] == 1


def test_free_throws_are_not_field_goal_attempts(app, client):
    gid = _create_game(client, "j1-ft")
    _tag_journey_one(client, gid)
    by_player, _ = _stats_by_player(client, gid)
    assert (by_player[AVERY]["pts"], by_player[AVERY]["fgm"], by_player[AVERY]["fga"]) == (9, 3, 5)
    # the persisted stats rows (rebuilt on every tag) agree
    rows = _query(app, "SELECT pts, fgm, fga FROM stats WHERE relational_game_id=? AND player_name=?",
                  (gid, AVERY))
    assert rows == [{"pts": 9, "fgm": 3, "fga": 5}]
    # a game of only free throws has points but no field goal attempts
    gid2 = _create_game(client, "j1-ft-only")
    _tag(client, gid2, "made_free_throw", "7", 1_000, "made")
    _tag(client, gid2, "missed_free_throw", "7", 2_000, "missed")
    by_player, _ = _stats_by_player(client, gid2)
    assert _pick(by_player["7"]) == _line(pts=1)


def test_four_factors_do_not_depend_on_shot_result_spelling(client):
    """The Film Tool's outcome picker sends 'make'; a coach tagging 'made_two' may send nothing.
    Player PTS already treat made_two/made_three as makes; team eFG% must agree."""
    gid = _create_game(client, "j1-make-spelling")
    _tag_journey_one(client, gid, made_result="make")
    by_player, _ = _stats_by_player(client, gid)
    assert by_player[AVERY]["pts"] == 9  # player side counts them
    ff = _ok(client.get(f"/api/four_factors/{gid}"))
    assert ff["efg_pct"] == round((5 + 0.5 * 2) / 7, 4)


def test_four_factors_count_accepted_ai_make_miss(app, client):
    gid = _create_game(client, "j1-ai-make-miss")
    for i, et in enumerate(("make", "make", "miss")):
        ev = _insert_ai_draft(app, gid, et, "4", 1_000 + i * 4_000)
        _ok(_post(client, f"/api/review/events/{ev}/accept", {}))
    by_player, _ = _stats_by_player(client, gid)
    assert _pick(by_player["4"], ("pts", "fgm", "fga")) == {"pts": 4, "fgm": 2, "fga": 3}
    assert _ok(client.get(f"/api/four_factors/{gid}"))["efg_pct"] == round(2 / 3, 4)


def test_program_ledger_counts_offensive_and_defensive_rebounds(client):
    gid = _create_game(client, "j1-ledger-reb")
    _tag_journey_one(client, gid)
    ledger = _ok(client.get(f"/api/program/{gid}/summary"))["ledger_box"]
    blake = next(p for p in ledger["players"] if p["player"] == BLAKE.lower())
    assert blake["reb"] == 3
    assert ledger["totals"]["reb"] == 3


# ── Journey 2: AI drafts -> coach review -> stats ────────────────────────────

def test_journey_ai_review_accept_correct_reject(app, client):
    gid = _create_game(client, "j2-ai")
    ids = {
        "make1": _insert_ai_draft(app, gid, "made_two", "1", 1_000, "made"),
        "miss1": _insert_ai_draft(app, gid, "missed_two", "1", 5_000, "missed"),
        "reb3": _insert_ai_draft(app, gid, "rebound_defensive", "3", 6_000),
        "to3": _insert_ai_draft(app, gid, "turnover", "3", 9_000),
        "stl5": _insert_ai_draft(app, gid, "steal", "5", 9_500),
        "ast3": _insert_ai_draft(app, gid, "assist", "3", 12_000),
        "three5": _insert_ai_draft(app, gid, "made_three", "5", 15_000, "made"),
    }

    # nothing trusted yet -> no official stats, and the review queue lists all 7 drafts
    by_player, _ = _stats_by_player(client, gid)
    assert by_player == {}
    queue = _ok(client.get(f"/api/review/events?game_id={gid}&review_status=pending"))
    assert [e["id"] for e in queue] == list(ids.values())

    # accept: make1, ast3
    for key in ("make1", "ast3"):
        body = _ok(_post(client, f"/api/review/events/{ids[key]}/accept", {"notes": "looks right"}))
        assert body["review_status"] == "accepted" and body["human_verified"] == 1
        assert body["reviewed_at"]
    # correct the rebounder (wrong player) and the timestamp
    body = _ok(_post(client, f"/api/review/events/{ids['reb3']}/correct",
                     {"player": "5", "timestamp_ms": 6_200, "notes": "it was #5"}))
    assert (body["review_status"], body["player"], body["timestamp_ms"]) == ("corrected", "5", 6_200)
    # reject: the turnover and the phantom three
    for key in ("to3", "three5"):
        body = _ok(_post(client, f"/api/review/events/{ids[key]}/reject", {"notes": "no"}))
        assert body["review_status"] == "rejected" and body["human_verified"] == 0
    # stl5 and miss1 stay pending

    # re-accepting an accepted event is idempotent; unknown ids 404
    again = _ok(_post(client, f"/api/review/events/{ids['make1']}/accept", {}))
    assert again["review_status"] == "accepted"
    assert _post(client, "/api/review/events/999999/accept", {}).status_code == 404
    assert _post(client, "/api/review/events/999999/reject", {}).status_code == 404
    assert _post(client, "/api/review/events/999999/correct", {"player": "2"}).status_code == 404
    # a no-op correction is refused and writes nothing
    assert _post(client, f"/api/review/events/{ids['reb3']}/correct", {"player": "5"}).status_code == 400
    assert _post(client, f"/api/review/events/{ids['reb3']}/correct", {}).status_code == 400

    by_player, _ = _stats_by_player(client, gid)
    assert set(by_player) == {"1", "3", "5"}
    assert _pick(by_player["1"]) == _line(pts=2, fgm=1, fga=1)          # miss1 still pending
    assert _pick(by_player["3"]) == _line(ast=1)                       # TO rejected, REB moved away
    assert _pick(by_player["5"]) == _line(reb=1)                       # steal pending, three rejected

    statuses = {r["id"]: r["review_status"] for r in _query(app, "SELECT id, review_status FROM events")}
    assert statuses == {
        ids["make1"]: "accepted", ids["miss1"]: "pending", ids["reb3"]: "corrected",
        ids["to3"]: "rejected", ids["stl5"]: "pending", ids["ast3"]: "accepted", ids["three5"]: "rejected",
    }

    # audit trail: one human_corrections row per changed field / rejection
    hc = _query(app, """SELECT event_id, correction_type, field_changed, original_value, corrected_value,
                               game_id, relational_game_id
                          FROM human_corrections ORDER BY id""")
    assert sorted((h["event_id"], h["correction_type"], h["field_changed"], h["original_value"],
                   h["corrected_value"]) for h in hc) == sorted([
        (ids["reb3"], "change_event", "player", "3", "5"),
        (ids["reb3"], "change_event", "timestamp_ms", "6000", "6200"),
        (ids["to3"], "remove_event", "review_status", "pending", "rejected"),
        (ids["three5"], "remove_event", "review_status", "pending", "rejected"),
    ])
    assert {(h["game_id"], h["relational_game_id"]) for h in hc} == {(str(gid), gid)}

    ri = {r["entity_id"]: r for r in _query(app, "SELECT * FROM review_items WHERE entity_type='event'")}
    assert {k: v["review_status"] for k, v in ri.items()} == {
        ids["make1"]: "accepted", ids["ast3"]: "accepted", ids["reb3"]: "corrected",
        ids["to3"]: "rejected", ids["three5"]: "rejected",
    }
    assert all(v["reviewed_at"] for v in ri.values())
    assert {v["relational_game_id"] for v in ri.values()} == {gid}

    prov = _query(app, "SELECT source_id, COUNT(*) AS n FROM provenance_records "
                       "WHERE entity_type='event' AND source_type='review' GROUP BY source_id")
    assert {p["source_id"]: p["n"] for p in prov} == {"accept_event": 2, "correct_event": 1, "reject_event": 2}

    # ledger view of the review queue = accepted + corrected only
    ledger = _ok(client.get(f"/api/review/events?game_id={gid}&review_status=ledger"))
    assert sorted(e["id"] for e in ledger) == sorted([ids["make1"], ids["ast3"], ids["reb3"]])
    assert _ok(client.get(f"/api/review/events?game_id={gid}&review_status=pending&count_only=1")) == {"count": 2}

    # a rejected event can be restored by accepting it
    _ok(_post(client, f"/api/review/events/{ids['three5']}/accept", {}))
    by_player, _ = _stats_by_player(client, gid)
    assert _pick(by_player["5"]) == _line(pts=3, fgm=1, fga=1, threes_made=1, threes_att=1, reb=1)


def test_corrected_event_type_changes_stats(app, client):
    gid = _create_game(client, "j2-correct-type")
    ev = _insert_ai_draft(app, gid, "missed_two", "1", 5_000, "missed")
    _ok(_post(client, f"/api/review/events/{ev}/correct", {"event_type": "made_three", "shot_result": "made"}))
    by_player, _ = _stats_by_player(client, gid)
    assert _pick(by_player["1"]) == _line(pts=3, fgm=1, fga=1, threes_made=1, threes_att=1)


def test_edited_event_type_changes_stats(client):
    gid = _create_game(client, "j2-edit-type")
    ev = _tag(client, gid, "made_two", "1", 1_000, "made")
    _ok(_put(client, f"/api/events/{ev}", {"event_type": "made_three"}))
    by_player, _ = _stats_by_player(client, gid)
    assert (by_player["1"]["pts"], by_player["1"]["threes_made"]) == (3, 1)


@pytest.mark.parametrize("use_analysis_key", [False, True], ids=["game-id", "film-analysis-key"])
def test_coach_added_ledger_event_counts_in_stats(app, client, use_analysis_key):
    """Film Tool '+ add event' posts to /api/review/events with the key the page is open on."""
    gid = _create_game(client, "j2-film-add")
    key = str(gid)
    if use_analysis_key:
        key = "film-j2-add"
        conn = _conn(app)
        conn.execute("INSERT INTO analysis_runs (game_id, analysis_key, video_path, status) "
                     "VALUES (?, ?, '/nonexistent/film.mp4', 'completed')", (gid, key))
        conn.commit()
        conn.close()
    created = _ok(_post(client, "/api/review/events",
                        {"game_id": key, "event_type": "made_three", "player": "1",
                         "shot_result": "made", "timestamp_ms": 4_000}), 201)
    assert created["review_status"] == "accepted"
    # the program ledger / official box (which match on the text key) already count it ...
    assert _ok(client.get(f"/api/program/{key}/summary"))["ledger_box"]["totals"]["pts"] == 3
    # ... the stats API must agree
    by_player, _ = _stats_by_player(client, key)
    assert by_player.get("1", {}).get("pts") == 3


def test_program_ledger_does_not_double_count_shot_make_pairs(app, client):
    """event_generator emits a 'shot' with shot_result plus a derived make/miss row for every attempt;
    stats._aggregate_rows skips the parent 'shot'. The program ledger/auto-ledger must too."""
    key = "film-ledger-pairs"
    for i, result in enumerate(("make", "miss")):
        _insert_ai_draft(app, key, "shot", "4", 1_000 + i * 5_000, result, relational=False)
        _insert_ai_draft(app, key, result, "4", 1_000 + i * 5_000, relational=False,
                         details={"derived_from": "shot"})
    promoted = _ok(_post(client, f"/api/program/{key}/auto-ledger", {}))
    assert promoted["promote"]["promoted_useful"] == 4
    # /api/stats agrees: one make, one miss
    by_player, _ = _stats_by_player(client, key)
    assert _pick(by_player["4"], ("pts", "fgm", "fga")) == {"pts": 2, "fgm": 1, "fga": 2}
    ledger = promoted["summary"]["ledger_box"]
    p4 = next(p for p in ledger["players"] if p["player"] == "4")
    assert (p4["pts"], p4["fgm"], p4["fga"]) == (2, 1, 2)


# ── Journey 3: stat book upload -> draft -> confirm -> official box ──────────

BOOK_PLAYERS = [
    # Liberty (home)
    {"jersey": "1", "name": "Avery Northwind", "team": "home", "fg2": 2, "fg3": 1, "ftm": 0, "fta": 2, "pts": 7},
    {"jersey": "3", "name": "Blake Ironwood", "team": "home", "fg2": 1, "fg3": 0, "ftm": 1, "fta": 1, "pts": 3},
    # Rival (away)
    {"jersey": "4", "name": "Opp Bravo", "team": "away", "fg2": 3, "fg3": 1, "ftm": 0, "fta": 0, "pts": 9},
]
BOOK_QUARTERS = [
    {"period": 1, "home_pts": 4, "away_pts": 2},
    {"period": 2, "home_pts": 2, "away_pts": 3},
    {"period": 3, "home_pts": 2, "away_pts": 2},
    {"period": 4, "home_pts": 2, "away_pts": 2},
]


def test_journey_scorebook_confirm_and_official_box(app, client, program_books):
    from tests.e2e import data as td
    from stat_book.schema import validate_confirmed_box

    gid = _create_game(client, "j3-book")
    key = str(gid)

    # 1) coach uploads a phone photo of the book -> a reviewable draft always exists
    upload = client.post(f"/stat-books/games/{key}/upload",
                         data={"scan": (io.BytesIO(td.png_bytes()), "book.png"),
                               "template_id": "liberty_spiral_scorebook"},
                         content_type="multipart/form-data")
    assert upload.status_code == 302 and upload.headers["Location"].endswith(f"/stat-books/games/{key}/review")
    draft = _ok(client.get(f"/stat-books/games/{key}/draft"))
    assert draft["box"]["game_id"] == key and draft["box"]["template_id"] == "liberty_spiral_scorebook"
    work = Path(app.config["UPLOAD_FOLDER"]) / "stat_books" / key
    assert (work / "original.png").is_file() and (work / "draft.json").is_file()
    assert _ok(client.get(f"/stat-books/games/{key}/review"), 200) is None  # HTML page renders

    # 2) "Re-check" with a typo (Blake pts 4) -> draft saved with a pts_identity issue
    typo = [dict(p) for p in BOOK_PLAYERS]
    typo[1]["pts"] = 4
    box_in = {"template_id": "liberty_spiral_scorebook", "home_team": "Liberty", "away_team": "Rival",
              "final_score_home": 10, "final_score_away": 9, "players": typo, "quarters": BOOK_QUARTERS}
    saved = _ok(_post(client, f"/stat-books/games/{key}/draft", {"box": box_in}))
    codes = sorted(i["code"] for i in saved["box"]["validation"]["issues"])
    assert codes == ["final_score_home_sum", "pts_identity"]
    assert _ok(client.get(f"/stat-books/games/{key}/draft"))["box"]["players"][1]["pts"] == 4

    # 3) fix + confirm
    box_in["players"] = BOOK_PLAYERS
    confirmed = _ok(_post(client, f"/stat-books/games/{key}/confirm",
                          {"box": box_in, "confirmed_by": "Coach E2E"}))
    assert confirmed["ok"] is True
    book = confirmed["box"]
    assert book["validation"] == {"ok": True, "issues": []}
    assert validate_confirmed_box(book) == []
    assert book["confirmed_by"] == "Coach E2E" and book["confirmed_at"].endswith("Z")
    assert Path(confirmed["path"]) == program_books.CONFIRMED_ROOT / f"{key}.json"
    avery_book = book["players"][0]
    assert (avery_book["fgm"], avery_book["tpm"], avery_book["extras"]) == (3, 1, {"fg2": 2, "fg3": 1})
    assert _ok(client.get(f"/stat-books/confirmed/{key}")) == book

    # 4) film tags for the counting stats the book does not record
    home = json.dumps({"team_side": "home"})
    away = json.dumps({"team_side": "away"})
    t = iter(range(10_000, 400_000, 7_000))
    _tag(client, gid, "rebound_defensive", "#1", next(t), details_json=home)
    _tag(client, gid, "rebound_defensive", "#1", next(t), details_json=home)
    _tag(client, gid, "assist", "#1", next(t), details_json=home)
    _tag(client, gid, "missed_two", "#1", next(t), "missed", details_json=home)
    _tag(client, gid, "made_two", "#1", next(t), "made", details_json=home)   # book already has PTS
    _tag(client, gid, "steal", "#3", next(t), details_json=home)
    _tag(client, gid, "turnover", "#3", next(t), details_json=home)
    _tag(client, gid, "rebound_offensive", "#3", next(t), details_json=home)
    _tag(client, gid, "block", "#4", next(t), details_json=away)
    _tag(client, gid, "rebound_defensive", "#4", next(t), details_json=away)

    summary = _ok(client.get(f"/api/program/{key}/summary"))
    assert summary["scorebook"]["present"] is True
    assert summary["scorebook"]["team_pts"] == 19
    box = summary["official_box"]
    assert box["scorebook_present"] is True
    assert box["opponent_name"] == "Rival"
    assert box["line_score_source"] == "scorebook"
    assert [(q["period"], q["liberty"], q["opponent"]) for q in box["line_score"]] == [
        ("Q1", 4, 2), ("Q2", 2, 3), ("Q3", 2, 2), ("Q4", 2, 2)]
    assert (box["line_score"][-1]["liberty_running"], box["line_score"][-1]["opponent_running"]) == (10, 9)
    assert box["final"] == {"liberty": 10, "opponent": 9}
    assert box["unassigned"] == []

    lib = {p["jersey"]: p for p in box["players"]["liberty"]}
    opp = {p["jersey"]: p for p in box["players"]["opponent"]}
    cols = ("pts", "fgm2", "fga2", "fgm3", "fga3", "ftm", "fta", "oreb", "dreb", "reb", "ast", "stl", "blk", "tov")
    # book PTS/makes kept; film adds the miss to 2PA and fills REB/AST/STL/BLK/TO
    assert {c: lib["1"][c] for c in cols} == dict(zip(cols, (7, 2, 3, 1, 1, 0, 2, 0, 2, 2, 1, 0, 0, 0)))
    assert {c: lib["3"][c] for c in cols} == dict(zip(cols, (3, 1, 1, 0, 0, 1, 1, 1, 0, 1, 0, 1, 0, 1)))
    assert {c: opp["4"][c] for c in cols} == dict(zip(cols, (9, 3, 3, 1, 1, 0, 0, 0, 1, 1, 0, 0, 1, 0)))
    assert lib["1"]["fg_pct"] == 75.0 and lib["1"]["ft_pct"] == 0.0
    team = box["team"]["liberty"]
    assert (team["pts"], team["reb"], team["ast"], team["stl"], team["tov"], team["fgm"], team["fga"]) == (10, 3, 1, 1, 1, 4, 5)
    assert (box["team"]["opponent"]["pts"], box["team"]["opponent"]["blk"]) == (9, 1)


def test_scorebook_confirm_rejects_bad_ids_and_shapes(client, program_books):
    before = sorted(p.name for p in program_books.CONFIRMED_ROOT.iterdir())
    for bad in ("..%2F..%2Fetc", "has space", "-leading-dash"):
        r = _post(client, f"/stat-books/games/{bad}/confirm", {"box": {"players": []}})
        assert r.status_code in (400, 404), bad
    assert client.get("/stat-books/confirmed/nope-not-here").status_code == 404
    # final score must be an int -> schema error, nothing written
    r = _post(client, "/stat-books/games/shape-check/confirm",
              {"box": {"players": [], "final_score_home": "ten"}})
    assert r.status_code == 400 and r.get_json()["error"] == "schema"
    # stat cells that are not numbers are dropped to null, not stored as text
    ok = _ok(_post(client, "/stat-books/games/shape-check/confirm",
                   {"box": {"players": [{"jersey": "7", "team": "home", "pts": "x", "ftm": "2"}]}}))
    assert ok["box"]["players"][0]["pts"] is None and ok["box"]["players"][0]["ftm"] == 2
    after = sorted(p.name for p in program_books.CONFIRMED_ROOT.iterdir())
    assert after == sorted(before + ["shape-check.json"])


def test_sample_scorebook_line_score_matches_final(client, program_books):
    r = client.post("/stat-books/sample", data={"game_id": "sample-e2e"})
    assert r.status_code == 302
    draft = _ok(client.get("/stat-books/games/sample-e2e/draft"))
    confirmed = _ok(_post(client, "/stat-books/games/sample-e2e/confirm", {"box": draft["box"]}))
    assert confirmed["box"]["final_score_home"] == 48
    box = _ok(client.get("/api/program/sample-e2e/summary"))["official_box"]
    assert box["line_score"][-1]["liberty_running"] == box["final"]["liberty"] == 48
    # per-period points, whose running totals are the book's 15-7, 23-22, 36-32, 48-49
    assert [(q["period"], q["liberty"], q["opponent"], q["liberty_running"], q["opponent_running"])
            for q in box["line_score"]] == [
        ("Q1", 15, 7, 15, 7), ("Q2", 8, 15, 23, 22), ("Q3", 13, 10, 36, 32), ("Q4", 12, 17, 48, 49)]


# ── Journey 4: edge cases ────────────────────────────────────────────────────

def test_game_with_no_events(client):
    gid = _create_game(client, "j4-empty")
    body = _ok(client.get(f"/api/stats/{gid}"))
    assert body["basic"] == []
    assert body["enhanced"]["possession_summary"]["total_possessions"] == 0
    assert _ok(client.get(f"/api/four_factors/{gid}")) == {
        "efg_pct": 0.0, "tov_pct": 0.0, "orb_pct": 0.0, "ft_rate": 0.0}
    assert client.get("/api/four_factors/987654").status_code == 404
    summary = _ok(client.get(f"/api/program/{gid}/summary"))
    assert summary["counts"] == {"pending": 0, "accepted": 0, "corrected": 0, "rejected": 0}
    assert summary["ledger_box"]["totals"]["pts"] == 0
    assert [e["code"] for e in summary["exceptions"]] == ["no_scorebook"]
    assert summary["official_box"]["final"] == {"liberty": 0, "opponent": 0}
    assert _ok(client.get(f"/api/events/{gid}")) == []


def test_save_event_validation_and_unknown_types(app, client):
    gid = _create_game(client, "j4-validate")
    bad = [
        ({"game_id": gid, "event_type": "made_two"}, "timestamp_ms required"),
        ({"game_id": gid, "timestamp_ms": 5}, "event_type required"),
        ({"game_id": gid, "event_type": "  ", "timestamp_ms": 5}, "event_type required"),
        ({"game_id": gid, "event_type": "made_two", "timestamp_ms": "soon"}, "timestamp_ms must be an integer"),
        ({"game_id": gid, "event_type": "made_two", "timestamp_ms": 5, "details_json": "{nope"}, "details_json must be valid JSON"),
        ({"game_id": gid, "event_type": "made_two", "timestamp_ms": 5, "details_json": 7}, "details_json must be a JSON object or array"),
        ({"event_type": "made_two", "timestamp_ms": 5}, "game_id required"),
        ({"game_id": "film-abc", "event_type": "made_two", "timestamp_ms": 5}, "game_id must be an existing game id"),
        ({"game_id": 987654, "event_type": "made_two", "timestamp_ms": 5}, "game_id must reference an existing game"),
    ]
    for payload, message in bad:
        r = _post(client, "/api/save_event", payload)
        assert r.status_code == 400, payload
        assert r.get_json()["message"] == message
    assert _query(app, "SELECT COUNT(*) AS n FROM events")[0]["n"] == 0

    # an unknown type is stored (bookmarks etc. use free text) but never counted
    _tag(client, gid, "dunk", "1", 1_000, "made")
    _tag(client, gid, "bookmark", "Coach note", 2_000)
    rows = _query(app, "SELECT event_type, event_type_id FROM events ORDER BY id")
    assert rows == [{"event_type": "dunk", "event_type_id": None}, {"event_type": "bookmark", "event_type_id": None}]
    by_player, _ = _stats_by_player(client, gid)
    assert by_player == {}
    # event type lookup is case-insensitive
    _tag(client, gid, "MADE_THREE", "1", 3_000, "made")
    by_player, _ = _stats_by_player(client, gid)
    assert _pick(by_player["1"]) == _line(pts=3, fgm=1, fga=1, threes_made=1, threes_att=1)
    # bookmarks filter
    marks = _ok(client.get(f"/api/events/{gid}?event_type=bookmark"))
    assert [m["player"] for m in marks] == ["Coach note"]


def test_duplicate_save_event_counts_twice(app, client):
    gid = _create_game(client, "j4-dup")
    payload = {"game_id": gid, "event_type": "made_two", "player": "1", "shot_result": "made", "timestamp_ms": 1_000}
    first = _ok(_post(client, "/api/save_event", payload))["id"]
    second = _ok(_post(client, "/api/save_event", payload))["id"]
    assert first != second  # save_event is not idempotent: a double click is two baskets
    # save_event rebuilt the persisted stats row after each tag
    assert _query(app, "SELECT pts, fgm, fga FROM stats WHERE relational_game_id=?", (gid,)) == [
        {"pts": 4, "fgm": 2, "fga": 2}]
    by_player, _ = _stats_by_player(client, gid)
    assert (by_player["1"]["pts"], by_player["1"]["fga"]) == (4, 2)


def test_delete_tag_rebuilds_persisted_stats(app, client):
    gid = _create_game(client, "j4-delete")
    keep = _tag(client, gid, "made_two", "1", 1_000, "made")
    extra = _tag(client, gid, "made_two", "1", 1_500, "made")
    assert _ok(client.delete(f"/api/events/{extra}")) == {"deleted": True}
    assert _query(app, "SELECT pts, fgm, fga FROM stats WHERE relational_game_id=?", (gid,)) == [
        {"pts": 2, "fgm": 1, "fga": 1}]
    assert _ok(client.delete(f"/api/events/{keep}")) == {"deleted": True}
    assert _query(app, "SELECT COUNT(*) AS n FROM stats WHERE relational_game_id=?", (gid,)) == [{"n": 0}]
    assert _ok(client.delete("/api/events/999999")) == {"deleted": True}


def test_delete_tag_after_viewing_stats(app, client):
    gid = _create_game(client, "j4-delete-after-stats")
    _tag(client, gid, "made_two", "1", 1_000, "made")
    extra = _tag(client, gid, "turnover", "1", 5_000)
    _stats_by_player(client, gid)  # coach opens the stats view (assigns possessions)
    resp = client.delete(f"/api/events/{extra}")
    assert resp.status_code == 200
    assert _query(app, "SELECT COUNT(*) AS n FROM events WHERE id=?", (extra,)) == [{"n": 0}]
    by_player, body = _stats_by_player(client, gid)
    assert (by_player["1"]["pts"], by_player["1"]["tov"]) == (2, 0)
    # no phantom possession is left behind: same summary as a game that only had the basket
    only_basket = _create_game(client, "j4-delete-after-stats-ref")
    _tag(client, only_basket, "made_two", "1", 1_000, "made")
    _stats_by_player(client, only_basket)  # first view assigns possessions, as above
    _, ref = _stats_by_player(client, only_basket)
    assert body["enhanced"]["possession_summary"] == ref["enhanced"]["possession_summary"]
    # deleting the last tag after viewing stats works too
    keep = _query(app, "SELECT id FROM events WHERE relational_game_id=?", (gid,))[0]["id"]
    assert client.delete(f"/api/events/{keep}").status_code == 200
    assert _stats_by_player(client, gid)[0] == {}


def test_pending_manual_event_waits_for_review(app, client):
    gid = _create_game(client, "j4-pending")
    ev = _tag(client, gid, "made_three", "2", 1_000, "made", human_verified=False)
    row = _query(app, "SELECT review_status, human_verified FROM events WHERE id=?", (ev,))[0]
    assert row == {"review_status": "pending", "human_verified": 0}
    items = _query(app, "SELECT entity_id, review_status, relational_game_id FROM review_items")
    assert items == [{"entity_id": ev, "review_status": "pending", "relational_game_id": gid}]
    assert _stats_by_player(client, gid)[0] == {}
    _ok(_post(client, f"/api/review/events/{ev}/accept", {}))
    assert _stats_by_player(client, gid)[0]["2"]["pts"] == 3
    assert _query(app, "SELECT review_status FROM review_items")[0]["review_status"] == "accepted"


def test_save_event_reviewed_at_is_a_timestamp_or_null(app, client):
    gid = _create_game(client, "j4-reviewed-at")
    accepted = _tag(client, gid, "steal", "1", 1_000)
    pending = _tag(client, gid, "steal", "1", 2_000, human_verified=False)
    rows = {r["id"]: r["reviewed_at"] for r in _query(app, "SELECT id, reviewed_at FROM events")}
    assert rows[pending] is None
    assert rows[accepted] not in ("accepted", "pending") and rows[accepted][:2] == "20"


def test_relational_and_analysis_keys_resolve_to_same_stats(app, client):
    gid = _create_game(client, "j4-keys")
    _tag(client, gid, "made_three", "1", 1_000, "made")
    _tag(client, gid, "rebound_defensive", "2", 2_000)
    _tag(client, gid, "assist", "2", 3_000)
    # the film analysis run for this game is keyed by a text analysis key
    conn = _conn(app)
    conn.execute("INSERT INTO analysis_runs (game_id, analysis_key, video_path, status) "
                 "VALUES (?, 'film-j4-keys', '/nonexistent/film.mp4', 'completed')", (gid,))
    conn.commit()
    conn.close()

    rel, _ = _stats_by_player(client, gid)
    by_key, _ = _stats_by_player(client, "film-j4-keys")
    assert rel == by_key
    assert _pick(rel["1"]) == _line(pts=3, fgm=1, fga=1, threes_made=1, threes_att=1)
    assert _pick(rel["2"]) == _line(reb=1, ast=1)

    # both calls rebuilt the same persisted rows (no duplicates per player)
    persisted = _query(app, "SELECT player_name, pts FROM stats WHERE relational_game_id=? ORDER BY player_name", (gid,))
    assert persisted == [{"player_name": "1", "pts": 3}, {"player_name": "2", "pts": 0}]
    # events API resolves the analysis key to the relational game as well
    assert [e["event_type"] for e in _ok(client.get("/api/events/film-j4-keys"))] == [
        "made_three", "rebound_defensive", "assist"]


def test_program_summary_does_not_read_scorebooks_outside_confirmed_dir(tmp_path, monkeypatch, client):
    import program_mode

    # the real scorebook_path/load_scorebook, rooted in a temp "repo" (not the program_books patch)
    monkeypatch.setattr(program_mode, "_repo_root", lambda: tmp_path / "repo")
    confirmed_dir = program_mode.scorebook_path("x").parent
    confirmed_dir.mkdir(parents=True)
    book = {"home_team": "Liberty", "away_team": "X", "final_score_home": 1,
            "players": [{"jersey": "1", "name": "Real Name", "team": "home", "pts": 1}]}
    (confirmed_dir / "legit-book.json").write_text(json.dumps(book))
    secret = tmp_path / "outside" / "secret.json"
    secret.parent.mkdir()
    secret.write_text(json.dumps({**book, "home_team": "LEAKED"}))

    # a confirmed book for a normal game id still loads
    legit = _ok(client.get("/api/program/legit-book/summary"))
    assert legit["scorebook"]["present"] is True and legit["scorebook"]["home_team"] == "Liberty"

    # a ../ game id that resolves to a JSON file outside confirmed/ is never read
    rel = os.path.relpath(secret.with_suffix(""), confirmed_dir)
    assert rel.startswith("..")
    summary = client.get(f"/api/program/{rel}/summary")
    body = summary.get_json() or {}
    assert summary.status_code in (200, 400, 404)
    assert (body.get("scorebook") or {}).get("present") is not True
    assert "LEAKED" not in summary.get_data(as_text=True)
