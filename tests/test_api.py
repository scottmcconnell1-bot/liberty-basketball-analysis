"""
test_api.py – Integration tests for all Flask API endpoints.
"""
import json
import io
from pathlib import Path
import pytest


# ── Helpers ───────────────────────────────────────────────────────────

def post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type="application/json")


def put_json(client, url, data):
    return client.put(url, data=json.dumps(data), content_type="application/json")


# ── Dashboard ─────────────────────────────────────────────────────────

def test_dashboard_returns_counts(client):
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    d = r.get_json()
    assert "seasons" in d
    assert "scheduled" in d
    assert "events" in d
    assert "players" in d
    assert "upcoming_games" in d
    assert "recent_events" in d


def test_resource_status_endpoint(client):
    r = client.get("/api/resource-status")
    assert r.status_code == 200
    d = r.get_json()
    assert "cpu" in d
    assert "memory" in d
    assert "gpu" in d
    assert "application" in d
    assert "power" in d
    assert "processes" in d["gpu"]


# ── Seasons ───────────────────────────────────────────────────────────

def test_seasons_empty(client):
    r = client.get("/api/seasons")
    assert r.status_code == 200
    assert r.get_json() == []


def test_create_season(client):
    r = post_json(client, "/api/seasons", {
        "name": "2025-26 Boys Jr High",
        "start_date": "2025-11-01",
        "end_date": "2026-02-28",
    })
    assert r.status_code == 201
    d = r.get_json()
    assert d["name"] == "2025-26 Boys Jr High"
    assert d["id"] is not None


def test_create_season_missing_field(client):
    r = post_json(client, "/api/seasons", {"name": "Incomplete"})
    assert r.status_code == 400


def test_create_season_duplicate(client):
    data = {"name": "Same", "start_date": "2025-01-01", "end_date": "2025-12-31"}
    post_json(client, "/api/seasons", data)
    r = post_json(client, "/api/seasons", data)
    assert r.status_code == 409


def test_get_season(client):
    r = post_json(client, "/api/seasons", {
        "name": "Test Season", "start_date": "2025-01-01", "end_date": "2025-12-31"
    })
    sid = r.get_json()["id"]
    r2 = client.get(f"/api/seasons/{sid}")
    assert r2.status_code == 200
    assert r2.get_json()["name"] == "Test Season"


def test_update_season(client):
    r = post_json(client, "/api/seasons", {
        "name": "Old Name", "start_date": "2025-01-01", "end_date": "2025-12-31"
    })
    sid = r.get_json()["id"]
    r2 = put_json(client, f"/api/seasons/{sid}", {"name": "New Name"})
    assert r2.status_code == 200
    assert r2.get_json()["name"] == "New Name"


def test_delete_season(client):
    r = post_json(client, "/api/seasons", {
        "name": "To Delete", "start_date": "2025-01-01", "end_date": "2025-12-31"
    })
    sid = r.get_json()["id"]
    r2 = client.delete(f"/api/seasons/{sid}")
    assert r2.status_code == 200
    r3 = client.get(f"/api/seasons/{sid}")
    assert r3.status_code == 404


# ── Scheduled Games ───────────────────────────────────────────────────

def _create_season(client):
    r = post_json(client, "/api/seasons", {
        "name": "2025-26", "start_date": "2025-11-01", "end_date": "2026-03-01"
    })
    return r.get_json()["id"]


def test_scheduled_games_empty(client):
    r = client.get("/api/scheduled_games")
    assert r.status_code == 200
    assert r.get_json() == []


def test_create_scheduled_game(client):
    sid = _create_season(client)
    r = post_json(client, "/api/scheduled_games", {
        "season_id": sid,
        "game_date": "2025-12-01",
        "opponent_name": "Riverside",
        "location_type": "home",
    })
    assert r.status_code == 201
    d = r.get_json()
    assert d["opponent_name"] == "Riverside"


def test_create_game_missing_fields(client):
    r = post_json(client, "/api/scheduled_games", {"season_id": 1})
    assert r.status_code == 400


def test_filter_games_by_season(client):
    s1 = _create_season(client)
    r2 = post_json(client, "/api/seasons", {
        "name": "Other Season", "start_date": "2026-01-01", "end_date": "2026-12-31"
    })
    s2 = r2.get_json()["id"]
    post_json(client, "/api/scheduled_games", {
        "season_id": s1, "game_date": "2025-12-01", "opponent_name": "TeamA"
    })
    post_json(client, "/api/scheduled_games", {
        "season_id": s2, "game_date": "2026-02-01", "opponent_name": "TeamB"
    })
    r = client.get(f"/api/scheduled_games?season_id={s1}")
    games = r.get_json()
    assert len(games) == 1
    assert games[0]["opponent_name"] == "TeamA"


def test_filter_games_by_level_and_gender(client):
    sid = _create_season(client)
    post_json(client, "/api/scheduled_games", {
        "season_id": sid,
        "game_date": "2025-12-01",
        "opponent_name": "Varsity Boys",
        "level": "varsity",
        "gender": "boys",
    })
    post_json(client, "/api/scheduled_games", {
        "season_id": sid,
        "game_date": "2025-12-02",
        "opponent_name": "JV Girls",
        "level": "jv",
        "gender": "girls",
    })
    r = client.get(f"/api/scheduled_games?season_id={sid}&level=jv&gender=girls")
    games = r.get_json()
    assert len(games) == 1
    assert games[0]["opponent_name"] == "JV Girls"


def test_update_scheduled_game(client):
    sid = _create_season(client)
    r = post_json(client, "/api/scheduled_games", {
        "season_id": sid, "game_date": "2025-12-01", "opponent_name": "Old Opp"
    })
    gid = r.get_json()["id"]
    r2 = put_json(client, f"/api/scheduled_games/{gid}", {"opponent_name": "New Opp"})
    assert r2.status_code == 200
    assert r2.get_json()["opponent_name"] == "New Opp"


def test_delete_scheduled_game(client):
    sid = _create_season(client)
    r = post_json(client, "/api/scheduled_games", {
        "season_id": sid, "game_date": "2025-12-01", "opponent_name": "DeleteMe"
    })
    gid = r.get_json()["id"]
    r2 = client.delete(f"/api/scheduled_games/{gid}")
    assert r2.status_code == 200
    r3 = client.get("/api/scheduled_games")
    assert not any(g["id"] == gid for g in r3.get_json())


def test_delete_season_cascades_games(client):
    sid = _create_season(client)
    post_json(client, "/api/scheduled_games", {
        "season_id": sid, "game_date": "2025-12-01", "opponent_name": "ShouldGoAway"
    })
    client.delete(f"/api/seasons/{sid}")
    r = client.get("/api/scheduled_games")
    assert r.get_json() == []


def test_create_and_update_game(client):
    sid = _create_season(client)
    scheduled = post_json(client, "/api/scheduled_games", {
        "season_id": sid,
        "game_date": "2025-12-10",
        "opponent_name": "Linked Opponent",
    }).get_json()
    r = post_json(client, "/api/games", {
        "scheduled_game_id": scheduled["id"],
        "source_type": "manual",
        "source_key": "manual-2025-12-10",
        "home_score": 55,
        "away_score": 47,
        "result": "win",
        "is_conference": True,
    })
    assert r.status_code == 201
    game = r.get_json()
    assert game["scheduled_game_id"] == scheduled["id"]
    gid = game["id"]

    r2 = put_json(client, f"/api/games/{gid}", {"source_key": "updated-key", "result": "loss"})
    assert r2.status_code == 200
    assert r2.get_json()["source_key"] == "updated-key"
    assert r2.get_json()["result"] == "loss"


def test_games_list_includes_schedule_context(client):
    sid = _create_season(client)
    scheduled = post_json(client, "/api/scheduled_games", {
        "season_id": sid,
        "game_date": "2025-12-11",
        "opponent_name": "Context Opponent",
    }).get_json()
    post_json(client, "/api/games", {
        "scheduled_game_id": scheduled["id"],
        "source_type": "manual",
        "source_key": "context-key",
    })
    r = client.get("/api/games")
    games = r.get_json()
    assert any(g.get("opponent_name") == "Context Opponent" for g in games)


def test_create_filter_and_delete_sources(client):
    sid = _create_season(client)
    scheduled = post_json(client, "/api/scheduled_games", {
        "season_id": sid,
        "game_date": "2025-12-12",
        "opponent_name": "Source Opponent",
    }).get_json()
    game = post_json(client, "/api/games", {
        "scheduled_game_id": scheduled["id"],
        "source_type": "manual",
        "source_key": "source-key",
    }).get_json()
    r = post_json(client, "/api/sources", {
        "game_id": game["id"],
        "source_type": "manual_upload",
        "source_path": "/tmp/source.mp4",
    })
    assert r.status_code == 201
    source = r.get_json()

    r2 = client.get(f"/api/sources?game_id={game['id']}")
    sources = r2.get_json()
    assert len(sources) == 1
    assert sources[0]["source_path"] == "/tmp/source.mp4"

    r3 = client.delete(f"/api/sources/{source['id']}")
    assert r3.status_code == 200
    assert client.get(f"/api/sources?game_id={game['id']}").get_json() == []


def test_confirm_nfhs_match_creates_game_and_source(client):
    sid = _create_season(client)
    scheduled = post_json(client, "/api/scheduled_games", {
        "season_id": sid,
        "game_date": "2025-12-13",
        "opponent_name": "NFHS Opponent",
    }).get_json()
    match = post_json(client, "/api/nfhs_matches", {
        "scheduled_game_id": scheduled["id"],
        "nfhs_game_id": "nfhs-123",
        "nfhs_url": "https://example.com/nfhs/123",
        "confidence": 0.88,
    }).get_json()

    r = client.post(f"/api/nfhs_matches/{match['id']}/confirm")
    assert r.status_code == 200
    confirmed = r.get_json()
    assert confirmed["match_status"] == "confirmed"
    assert confirmed["game_id"] is not None

    games = client.get("/api/games").get_json()
    linked_game = next(g for g in games if g["scheduled_game_id"] == scheduled["id"])
    assert linked_game["nfhs_game_id"] == "nfhs-123"

    sources = client.get(f"/api/sources?game_id={linked_game['id']}").get_json()
    assert len(sources) == 1
    assert sources[0]["source_type"] == "nfhs_vod"
    assert sources[0]["source_path"] == "https://example.com/nfhs/123"


def test_reject_nfhs_match(client):
    sid = _create_season(client)
    scheduled = post_json(client, "/api/scheduled_games", {
        "season_id": sid,
        "game_date": "2025-12-14",
        "opponent_name": "Reject Opponent",
    }).get_json()
    match = post_json(client, "/api/nfhs_matches", {
        "scheduled_game_id": scheduled["id"],
        "nfhs_game_id": "nfhs-456",
        "nfhs_url": "https://example.com/nfhs/456",
    }).get_json()

    r = client.post(f"/api/nfhs_matches/{match['id']}/reject")
    assert r.status_code == 200
    assert r.get_json()["match_status"] == "rejected"


# ── Events ────────────────────────────────────────────────────────────

def test_save_event(client):
    r = post_json(client, "/api/save_event", {
        "game_id": "game1",
        "event_type": "shot",
        "timestamp_ms": 5000,
        "player": "Player1",
        "shot_result": "made",
    })
    assert r.status_code == 200
    assert r.get_json()["status"] == "success"


def test_save_event_missing_timestamp(client):
    r = post_json(client, "/api/save_event", {"game_id": "game1", "event_type": "shot"})
    assert r.status_code == 400


def test_get_events(client):
    post_json(client, "/api/save_event", {"game_id": "gX", "event_type": "assist", "timestamp_ms": 1000})
    post_json(client, "/api/save_event", {"game_id": "gX", "event_type": "rebound", "timestamp_ms": 2000})
    r = client.get("/api/events/gX")
    events = r.get_json()
    assert len(events) == 2
    assert events[0]["timestamp_ms"] < events[1]["timestamp_ms"]


def test_get_events_can_filter_by_event_type(client):
    post_json(client, "/api/save_event", {
        "game_id": "bookmark_game",
        "event_type": "bookmark",
        "timestamp_ms": 1000,
        "player": "Clip A",
    })
    post_json(client, "/api/save_event", {
        "game_id": "bookmark_game",
        "event_type": "assist",
        "timestamp_ms": 2000,
    })
    r = client.get("/api/events/bookmark_game?event_type=bookmark")
    events = r.get_json()
    assert len(events) == 1
    assert events[0]["event_type"] == "bookmark"


def test_update_event(client):
    r = post_json(client, "/api/save_event", {
        "game_id": "g1", "event_type": "shot", "timestamp_ms": 1000
    })
    eid = r.get_json()["id"]
    r2 = put_json(client, f"/api/events/{eid}", {"event_type": "block"})
    assert r2.status_code == 200
    assert r2.get_json()["event_type"] == "block"


def test_delete_event(client):
    r = post_json(client, "/api/save_event", {
        "game_id": "g1", "event_type": "steal", "timestamp_ms": 500
    })
    eid = r.get_json()["id"]
    r2 = client.delete(f"/api/events/{eid}")
    assert r2.status_code == 200
    r3 = client.get("/api/events/g1")
    assert not any(e["id"] == eid for e in r3.get_json())


# ── Players ───────────────────────────────────────────────────────────

def test_players_empty(client):
    r = client.get("/api/players")
    assert r.status_code == 200
    assert r.get_json() == []


def test_create_player(client):
    r = post_json(client, "/api/players", {
        "name": "Jordan Smith", "jersey_number": 23, "position": "G", "grade": 8
    })
    assert r.status_code == 201
    d = r.get_json()
    assert d["name"] == "Jordan Smith"
    assert d["jersey_number"] == 23


def test_create_player_missing_name(client):
    r = post_json(client, "/api/players", {"jersey_number": 5})
    assert r.status_code == 400


# ── Pages render ─────────────────────────────────────────────────────

def test_index_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"Liberty" in r.data


def test_schedule_page(client):
    r = client.get("/schedule")
    assert r.status_code == 200
    assert b"Schedule" in r.data


def test_schedule_page_renders_games_server_side(client):
    sid = _create_season(client)
    post_json(client, "/api/scheduled_games", {
        "season_id": sid,
        "game_date": "2025-12-05",
        "opponent_name": "Server Render Opponent",
        "level": "varsity",
        "gender": "girls",
    })
    r = client.get(f"/schedule?season_id={sid}&level=varsity&gender=girls")
    assert r.status_code == 200
    assert b"Server Render Opponent" in r.data


def test_games_page_renders_server_side(client):
    sid = _create_season(client)
    scheduled = post_json(client, "/api/scheduled_games", {
        "season_id": sid,
        "game_date": "2025-12-20",
        "opponent_name": "Rendered Game Opponent",
    }).get_json()
    post_json(client, "/api/games", {
        "scheduled_game_id": scheduled["id"],
        "source_type": "manual",
        "source_key": "rendered-game-key",
    })
    r = client.get("/games")
    assert r.status_code == 200
    assert b"Rendered Game Opponent" in r.data


def test_nfhs_matches_page_renders_server_side(client):
    sid = _create_season(client)
    scheduled = post_json(client, "/api/scheduled_games", {
        "season_id": sid,
        "game_date": "2025-12-21",
        "opponent_name": "Rendered NFHS Opponent",
    }).get_json()
    post_json(client, "/api/nfhs_matches", {
        "scheduled_game_id": scheduled["id"],
        "nfhs_game_id": "nfhs-rendered",
        "nfhs_url": "https://example.com/rendered",
    })
    r = client.get("/nfhs-matches")
    assert r.status_code == 200
    assert b"Rendered NFHS Opponent" in r.data


def test_practices_page_renders_server_side(client):
    sid = _create_season(client)
    r = client.post("/practices/save", data={
        "season_id": sid,
        "practice_date": "2025-12-22",
        "level": "varsity",
        "status": "planned",
        "plan_source": "manual",
        "plan_text": "Shell defense and transition offense",
        "coach_notes": "Good energy.",
        "filter_season_id": sid,
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b"2025-12-22" in r.data
    assert b"Good energy." in r.data


def test_practice_report_generation(client):
    sid = _create_season(client)
    client.post("/practices/save", data={
        "season_id": sid,
        "practice_date": "2025-12-23",
        "level": "jv",
        "status": "completed",
        "plan_source": "manual",
        "plan_text": "Rebounding and transition defense",
        "coach_notes": "Too many second chances allowed.",
    }, follow_redirects=True)
    report_page = client.get("/practices")
    assert report_page.status_code == 200
    assert b"2025-12-23" in report_page.data

    # Pull the first practice ID through the report link in the rendered page by assuming a single practice exists.
    practices_page_html = report_page.data.decode("utf-8")
    marker = '/practices/'
    start = practices_page_html.index(marker) + len(marker)
    practice_id = int(practices_page_html[start:practices_page_html.index('/report', start)])

    generated = client.post(f"/practices/{practice_id}/generate", follow_redirects=True)
    assert generated.status_code == 200
    assert b"AI Notes" in generated.data
    assert b"Likely emphasis area" in generated.data


def test_practice_summary_page(client):
    sid = _create_season(client)
    client.post("/practices/save", data={
        "season_id": sid,
        "practice_date": "2025-12-24",
        "level": "varsity",
        "status": "completed",
        "plan_source": "manual",
        "plan_text": "Shooting and spacing",
        "coach_notes": "Shot quality improved late.",
    }, follow_redirects=True)
    client.post("/practices/save", data={
        "season_id": sid,
        "practice_date": "2025-12-26",
        "level": "varsity",
        "status": "completed",
        "plan_source": "manual",
        "plan_text": "Shooting and rebounding",
        "coach_notes": "Needed more box-outs.",
    }, follow_redirects=True)
    r = client.get("/practice-summary?start_date=2025-12-20&end_date=2025-12-31&level=varsity")
    assert r.status_code == 200
    assert b"Range Summary" in r.data
    assert b"Recurring themes" in r.data


def test_film_page(client):
    r = client.get("/film")
    assert r.status_code == 200
    assert b"Report Bug / Idea" in r.data
    assert b"filmReviewGrid" in r.data
    assert b"aiEventsPanel" in r.data
    assert b"aiEventsScroller" in r.data
    assert b"aiCurrentEventLabel" in r.data
    assert b"Independent scrolling event timeline" in r.data


def test_film_page_accepts_manual_game_id_query(client):
    r = client.get("/film?game_id=manual_clip_01")
    assert r.status_code == 200
    assert b"manual_clip_01" in r.data
    assert b"uploadProgressBar" in r.data


def test_film_page_with_uploaded_filename_embeds_video_url(client):
    r = client.get("/film/test_clip.mp4?game_id=test_game")
    assert r.status_code == 200
    assert b"/uploads/test_clip.mp4" in r.data
    assert b"Server video" in r.data


def test_film_tool_ai_events_doc_exists():
    doc = Path("docs/FILM_TOOL_AI_EVENTS.md").read_text(encoding="utf-8")
    assert "independently scrollable panel" in doc
    assert "Playback-linked highlighting" in doc


def test_upload_route_returns_json_for_xhr(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module.subprocess, "Popen", lambda *args, **kwargs: None)

    r = client.post(
        "/upload",
        data={
            "video": (io.BytesIO(b"video-bytes"), "sample.mp4"),
            "opponent": "Test Opponent",
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["status"] == "uploaded"
    assert payload["redirect_url"].startswith("/film/")
    assert "game_id=" in payload["redirect_url"]


def test_analysis_status_includes_counts_and_summary(client, db):
    db.execute(
        "INSERT INTO analysis_runs (game_id, video_path, status) VALUES (?, ?, ?)",
        ("analysis_game", "uploads/demo.mp4", "completed"),
    )
    db.execute(
        """INSERT INTO detections
           (game_id, frame_number, timestamp_ms, object_class, confidence, x_center, y_center, width, height)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("analysis_game", 1, 100, "person", 0.9, 10, 10, 20, 40),
    )
    db.execute(
        """INSERT INTO events
           (game_id, event_type, timestamp_ms, human_verified)
           VALUES (?, ?, ?, ?)""",
        ("analysis_game", "bookmark", 100, 1),
    )
    db.commit()

    r = client.get("/api/analysis_status/analysis_game")
    payload = r.get_json()
    assert r.status_code == 200
    assert payload["status"] == "completed"
    assert payload["detection_count"] == 1
    assert payload["event_count"] == 1
    assert "YOLO currently detects players and the ball" in payload["event_generation_summary"]


def test_settings_page_renders(client):
    r = client.get("/settings")
    assert r.status_code == 200
    assert b"Settings" in r.data
    assert b"Report Bug / Idea" in r.data
    assert b"Debug / Issues" in r.data
    assert b"Detector Model" in r.data
    assert b"Event Generator" in r.data
    assert b"Expanded heuristic generator" in r.data
    assert b"Custom Weights Guide" in r.data
    assert b"YOLO11 Small" in r.data
    assert b"Custom Ultralytics Model or Weights" in r.data
    assert b"Recommended Ollama Models" in r.data


def test_custom_weights_guide_page_renders(client):
    r = client.get("/settings/custom-weights")
    assert r.status_code == 200
    assert b"Custom Weights Guide" in r.data
    assert b"Can Ollama Vision Models Be Used?" in r.data
    assert b"How to Create Your Own Custom Weights" in r.data
    assert b"dataset.yaml" in r.data


def test_debug_page_renders(client):
    r = client.get("/debug")
    assert r.status_code == 200
    assert b"Debug / Issues" in r.data
    assert b"Report Bug, Issue, or Recommendation" in r.data
    assert b"Application Logs" in r.data


def test_create_and_complete_issue_report(client, db):
    created = client.post("/debug/issues", data={
        "entry_type": "recommendation",
        "title": "Add better rebounding tags",
        "details": "Need clearer offensive and defensive rebound labeling.",
        "browser_console": "[2026-05-05T07:00:00Z] ERROR clip load failed",
        "return_to": "/film?game=1#clips",
    }, headers={"X-Requested-With": "XMLHttpRequest"})
    assert created.status_code == 200
    assert created.get_json()["message"] == "Report saved."

    row = db.execute("SELECT * FROM issue_reports WHERE title = ?", ("Add better rebounding tags",)).fetchone()
    assert row is not None
    assert row["status"] == "open"
    assert row["source_path"] == "/film?game=1#clips"
    assert "clip load failed" in row["browser_console"]

    completed = client.post(f"/debug/issues/{row['id']}/complete", data={"return_to": "/debug"}, follow_redirects=True)
    assert completed.status_code == 200

    updated = db.execute("SELECT status, completed_at FROM issue_reports WHERE id = ?", (row["id"],)).fetchone()
    assert updated["status"] == "completed"
    assert updated["completed_at"] is not None
    assert b"Completed" in completed.data


def test_debug_page_prefills_source_from_referrer(client):
    r = client.get("/debug", headers={"Referer": "http://localhost/film?game=44#reports"})
    assert r.status_code == 200
    assert b"/film?game=44" in r.data


def test_debug_page_filters_completed_reports(client, db):
    db.execute(
        """INSERT INTO issue_reports (entry_type, title, details, status)
           VALUES (?, ?, ?, ?)""",
        ("bug", "Open issue", "Still broken", "open"),
    )
    db.execute(
        """INSERT INTO issue_reports (entry_type, title, details, status, completed_at)
           VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        ("note", "Completed issue", "Already fixed", "completed"),
    )
    db.commit()

    r = client.get("/debug?entry_status=completed")
    assert r.status_code == 200
    assert b"Completed issue" in r.data
    assert b"Open issue" not in r.data


def test_settings_page_persists_updates(client, db):
    r = client.post("/settings", data={
        "feature_ENABLE_MANUAL_TAG_MVP": "on",
        "feature_ENABLE_AUTO_STATS_M1": "on",
        "feature_ENABLE_SEASONS_SCHEDULE": "on",
        "feature_ENABLE_GAMES_SOURCES": "on",
        "feature_ENABLE_NFHS_MATCHING": "on",
        "feature_ENABLE_PRACTICES": "on",
        "analysis_USE_DRIBBLE_HEURISTICS": "on",
        "ai_detector_model": "custom",
        "ai_custom_detector_model": "yolo11s.pt",
        "ai_inference_device": "cpu",
        "ai_event_generator_mode": "expanded",
        "ai_frame_stride": "2",
        "ai_tracker_max_distance": "95",
        "ai_tracker_max_frame_gap": "7",
        "ai_llm_provider": "none",
        "ai_llm_model": "",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b"Settings saved." in r.data

    rows = db.execute("SELECT key, value FROM app_settings").fetchall()
    stored = {row["key"]: row["value"] for row in rows}
    assert stored["ai.detector_model"] == "custom"
    assert stored["ai.custom_detector_model"] == "yolo11s.pt"
    assert stored["ai.inference_device"] == "cpu"
    assert stored["ai.event_generator_mode"] == "expanded"
    assert stored["ai.frame_stride"] == "2"
    assert stored["ai.tracker_max_distance"] == "95"
    assert stored["analysis.USE_DRIBBLE_HEURISTICS"] == "1"


def test_pull_ollama_model_starts_background_pull(client, monkeypatch):
    import app as app_module

    calls = []

    class DummyPopen:
        def __init__(self, cmd, stdout=None, stderr=None, start_new_session=None):
            calls.append({
                "cmd": cmd,
                "stdout_name": getattr(stdout, "name", None),
                "stderr": stderr,
                "start_new_session": start_new_session,
            })

    monkeypatch.setattr(app_module.subprocess, "Popen", DummyPopen)

    r = client.post("/settings/ollama/pull", data={"model_name": "qwen2.5:7b"}, follow_redirects=False)
    assert r.status_code == 302
    assert "/settings?message=Started+pulling+qwen2.5:7b" in r.headers["Location"]
    assert calls
    assert calls[0]["cmd"] == ["ollama", "pull", "qwen2.5:7b"]
    assert calls[0]["stdout_name"].endswith("liberty-basketball-ollama-pull-qwen2.5-7b.log")
    assert calls[0]["start_new_session"] is True


def test_pull_ollama_model_rejects_invalid_name(client):
    r = client.post("/settings/ollama/pull", data={"model_name": "bad model"}, follow_redirects=False)
    assert r.status_code == 302
    assert "/settings?message=Invalid+Ollama+model+name." in r.headers["Location"]


def test_compare_video_analysis_page(client, db):
    db.execute(
        """INSERT INTO videos
           (original_filename, stored_filename, file_path, file_size_bytes, opponent, game_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("sample.mp4", "sample_1.mp4", "uploads/sample_1.mp4", 123, "Test Opponent", "base_game"),
    )
    db.execute(
        """INSERT INTO analysis_runs
           (game_id, video_path, source_video_id, base_game_id, run_label, run_kind, status)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("base_game", "uploads/sample_1.mp4", 1, "base_game", "Original upload", "primary", "completed"),
    )
    db.execute(
        """INSERT INTO analysis_runs
           (game_id, video_path, source_video_id, base_game_id, run_label, run_kind, status)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("base_game__rerun_1", "uploads/sample_1.mp4", 1, "base_game", "Rerun A", "rerun", "completed"),
    )
    db.commit()

    r = client.get("/videos/1/compare")
    assert r.status_code == 200
    assert b"Compare AI Runs" in r.data
    assert b"Original upload" in r.data
    assert b"Rerun A" in r.data


def test_rerun_video_analysis_creates_separate_run(client, db, monkeypatch):
    import app as app_module

    db.execute(
        """INSERT INTO videos
           (original_filename, stored_filename, file_path, file_size_bytes, opponent, game_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("sample.mp4", "sample_2.mp4", "uploads/sample_2.mp4", 123, "Test Opponent", "base_game"),
    )
    db.execute(
        "INSERT INTO analysis_runs (game_id, video_path, status) VALUES (?, ?, ?)",
        ("base_game", "uploads/sample_2.mp4", "completed"),
    )
    db.commit()

    monkeypatch.setattr(app_module, "ai_runtime_available", lambda: True)
    monkeypatch.setattr(app_module, "start_analysis_subprocess", lambda *args, **kwargs: None)

    r = client.post("/videos/1/rerun", data={"run_label": "YOLOv8s retry"}, follow_redirects=True)
    assert r.status_code == 200
    assert b"Queued rerun" in r.data
    assert b"YOLOv8s retry" in r.data

    rows = db.execute(
        "SELECT game_id, base_game_id, run_label, run_kind, settings_json FROM analysis_runs ORDER BY id"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["game_id"] == "base_game"
    assert rows[1]["game_id"] != "base_game"
    assert rows[1]["base_game_id"] == "base_game"
    assert rows[1]["run_label"] == "YOLOv8s retry"
    assert rows[1]["run_kind"] == "rerun"
    assert "detector_model" in rows[1]["settings_json"]


# ── Stats ─────────────────────────────────────────────────────────────

def test_stats_empty_game(client):
    r = client.get("/api/stats/no_such_game")
    assert r.status_code == 200
    assert r.get_json() == []


def test_stats_aggregation(client):
    for _ in range(3):
        post_json(client, "/api/save_event", {
            "game_id": "sg1", "player": "Alice",
            "event_type": "two_attempt", "shot_result": "made", "timestamp_ms": 1000
        })
    post_json(client, "/api/save_event", {
        "game_id": "sg1", "player": "Alice",
        "event_type": "assist", "timestamp_ms": 2000
    })
    r = client.get("/api/stats/sg1")
    stats = r.get_json()
    alice = next(s for s in stats if s["player"] == "Alice")
    assert alice["pts"] == 6
    assert alice["fgm"] == 3
    assert alice["ast"] == 1


def test_stats_are_persisted_to_table(client, db):
    post_json(client, "/api/save_event", {
        "game_id": "persisted_stats_game",
        "player": "Taylor",
        "event_type": "three_attempt",
        "shot_result": "made",
        "timestamp_ms": 1000,
    })
    client.get("/api/stats/persisted_stats_game")
    row = db.execute(
        "SELECT player_name, pts, threes_made FROM stats WHERE game_id=?",
        ("persisted_stats_game",),
    ).fetchone()
    assert row is not None
    assert row["player_name"] == "Taylor"
    assert row["pts"] == 3
    assert row["threes_made"] == 1


def test_schedule_routes_hidden_when_feature_disabled(app, client):
    original = app.config["FEATURES"]["ENABLE_SEASONS_SCHEDULE"]
    app.config["FEATURES"]["ENABLE_SEASONS_SCHEDULE"] = False
    try:
        assert client.get("/schedule").status_code == 404
        assert client.get("/api/scheduled_games").status_code == 404
    finally:
        app.config["FEATURES"]["ENABLE_SEASONS_SCHEDULE"] = original


def test_games_routes_hidden_when_feature_disabled(app, client):
    original = app.config["FEATURES"]["ENABLE_GAMES_SOURCES"]
    app.config["FEATURES"]["ENABLE_GAMES_SOURCES"] = False
    try:
        assert client.get("/games").status_code == 404
        assert client.get("/api/games").status_code == 404
        assert client.get("/api/sources").status_code == 404
    finally:
        app.config["FEATURES"]["ENABLE_GAMES_SOURCES"] = original


def test_auto_stats_routes_hidden_when_feature_disabled(app, client):
    original = app.config["FEATURES"]["ENABLE_AUTO_STATS_M1"]
    app.config["FEATURES"]["ENABLE_AUTO_STATS_M1"] = False
    try:
        assert client.get("/api/stats/no_such_game").status_code == 404
        assert client.get("/api/analysis_status/no_such_game").status_code == 404
        assert client.get("/videos").status_code == 404
        assert client.get("/api/videos").status_code == 404
        assert client.get("/status").status_code == 404
    finally:
        app.config["FEATURES"]["ENABLE_AUTO_STATS_M1"] = original
