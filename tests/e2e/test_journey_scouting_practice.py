"""E2E journeys: scouting, practice plans & playlists, player development,
read-only assistant, status/preview pages.

Every journey drives the real Flask routes against the temp DB from tests/conftest.py and
asserts exact outcomes. Tests marked xfail(strict=True) document verified bugs: they assert
the CORRECT behaviour and will start failing (XPASS) once the bug is fixed.
"""
from __future__ import annotations

import json
import re
import sqlite3

import pytest

pytestmark = pytest.mark.e2e

JSON = "application/json"


# ── helpers ──────────────────────────────────────────────────────────────────

@pytest.fixture
def web(app, client, monkeypatch):
    """Client that turns unhandled exceptions into HTTP 500 (instead of raising), and never
    reaches a real LLM."""
    import helpers

    monkeypatch.setitem(app.config, "PROPAGATE_EXCEPTIONS", False)
    monkeypatch.setattr(helpers, "list_ollama_models", lambda *a, **k: [])
    monkeypatch.setattr(helpers, "call_ollama", lambda *a, **k: (False, ""))
    return client


def raw(app) -> sqlite3.Connection:
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def q(app, sql, params=()):
    conn = raw(app)
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def send(client, method, url, payload=None):
    kw = {}
    if payload is not None:
        kw = {"data": json.dumps(payload), "content_type": JSON}
    return getattr(client, method)(url, **kw)


def ok_json(resp, *codes):
    codes = codes or (200,)
    assert resp.status_code in codes, f"{resp.status_code}: {resp.data[:300]!r}"
    return resp.get_json()


def create_game(client, key):
    return ok_json(send(client, "post", "/api/games", {"source_type": "manual", "source_key": key}), 201)["id"]


def save_event(client, game_id, player, event_type, ts, *, status="accepted", shot_result="made"):
    """Create an AI-style pending event and move it to `status` through the review routes."""
    ev = ok_json(send(client, "post", "/api/save_event", {
        "game_id": game_id, "player": player, "event_type": event_type,
        "shot_result": shot_result, "timestamp_ms": ts, "human_verified": False, "source_type": "ai",
    }), 200, 201)
    eid = ev["id"]
    if status == "accepted":
        ok_json(send(client, "post", f"/api/review/events/{eid}/accept", {"notes": "ok"}))
    elif status == "rejected":
        ok_json(send(client, "post", f"/api/review/events/{eid}/reject", {"notes": "no"}))
    return eid


def create_player(app, name, jersey):
    conn = raw(app)
    cur = conn.execute("INSERT INTO players (name, jersey_number) VALUES (?, ?)", (name, jersey))
    conn.commit()
    pid = cur.lastrowid
    conn.close()
    return pid


def create_season(client, app, name="2026-27"):
    r = client.post("/schedule/seasons/save", data={
        "name": name, "start_date": "2026-11-01", "end_date": "2027-03-01", "season_type": "regular",
    })
    assert r.status_code in (200, 302), r.data[:200]
    return q(app, "SELECT id FROM seasons WHERE name=?", (name,))[0]["id"]


def ask(client, question, game_id, player=None):
    payload = {"question": question, "game_id": game_id}
    if player is not None:
        payload["player"] = player
    return ok_json(send(client, "post", "/api/assistant/query", payload))


def default_team_id(app):
    with app.app_context():
        from helpers import get_db, get_default_team_id
        return get_default_team_id(get_db())


def set_entitlement(app, key, enabled):
    team_id = default_team_id(app)
    conn = raw(app)
    conn.execute(
        "INSERT OR REPLACE INTO module_entitlements (team_id, module_key, enabled, notes) VALUES (?,?,?,?)",
        (team_id, key, int(enabled), "e2e"),
    )
    conn.commit()
    conn.close()


# ── 1. Scouting ──────────────────────────────────────────────────────────────

def test_scouting_journey_reports_isolated_by_opponent(web, app):
    c = web
    game = create_game(c, "scout-film-1")
    a = ok_json(send(c, "post", "/api/scouting/reports", {
        "opponent_name": "Eagle Ridge", "scout_date": "2026-01-10", "film_source": "manual_upload", "game_id": game,
    }), 201)["id"]
    b = ok_json(send(c, "post", "/api/scouting/reports", {
        "opponent_name": "Falcon Creek", "scout_date": "2026-01-12", "film_source": "nfhs_vod",
    }), 201)["id"]

    # Attach children to A (clips inserted out of order) and one clip to B.
    for clip in (
        {"clip_type": "offensive_set", "quarter": 3, "game_time": "Q3 4:10", "description": "A-horns", "coach_cue": "Switch"},
        {"clip_type": "tendency", "quarter": 1, "game_time": "Q1 6:00", "description": "A-press", "coach_cue": "Middle"},
        {"clip_type": "mismatch", "quarter": 1, "game_time": "Q1 2:30", "description": "A-post", "source": "ai_detected"},
    ):
        ok_json(send(c, "post", f"/api/scouting/reports/{a}/clips", clip), 201)
    ok_json(send(c, "post", f"/api/scouting/reports/{b}/clips",
                 {"clip_type": "situational", "quarter": 4, "description": "B-ATO"}), 201)
    ok_json(send(c, "post", f"/api/scouting/reports/{a}/personnel",
                 {"jersey_number": 21, "player_name": "Opp Charlie", "role": "go_to_scorer", "notes": "left hand"}), 201)
    ok_json(send(c, "post", f"/api/scouting/reports/{a}/offensive-sets",
                 {"set_name": "Horns", "frequency": 7, "ppp": 1.1}), 201)
    ok_json(send(c, "post", f"/api/scouting/reports/{a}/offensive-sets",
                 {"set_name": "Motion", "frequency": 12}), 201)
    ok_json(send(c, "post", f"/api/scouting/reports/{a}/practice-points",
                 {"point_number": 2, "description": "deny #21"}), 201)
    ok_json(send(c, "post", f"/api/scouting/reports/{a}/practice-points",
                 {"point_number": 1, "description": "sprint back"}), 201)

    # List: both reports, newest scout_date first; filter by opponent client-side.
    listing = ok_json(c.get("/api/scouting/reports"))
    assert [r["opponent_name"] for r in listing] == ["Falcon Creek", "Eagle Ridge"]
    assert [r["id"] for r in listing if r["opponent_name"] == "Eagle Ridge"] == [a]

    full_a = ok_json(c.get(f"/api/scouting/reports/{a}"))
    assert full_a["report"]["game_id"] == game
    assert [x["description"] for x in full_a["clips"]] == ["A-post", "A-press", "A-horns"]  # quarter, game_time
    assert [x["set_name"] for x in full_a["offensive_sets"]] == ["Motion", "Horns"]           # frequency desc
    assert [x["description"] for x in full_a["practice_points"]] == ["sprint back", "deny #21"]
    assert [(p["player_name"], p["jersey_number"]) for p in full_a["personnel"]] == [("Opp Charlie", 21)]

    full_b = ok_json(c.get(f"/api/scouting/reports/{b}"))
    assert [x["description"] for x in full_b["clips"]] == ["B-ATO"]
    assert full_b["personnel"] == [] and full_b["offensive_sets"] == [] and full_b["practice_points"] == []
    assert [x["description"] for x in ok_json(c.get(f"/api/scouting/reports/{b}/clips"))] == ["B-ATO"]

    # Edit A.
    ok_json(send(c, "put", f"/api/scouting/reports/{a}", {
        "opponent_name": "Eagle Ridge JV", "status": "completed", "tempo": "fast", "executive_summary": "Press early",
    }))
    rep = ok_json(c.get(f"/api/scouting/reports/{a}"))["report"]
    assert (rep["opponent_name"], rep["status"], rep["tempo"], rep["executive_summary"]) == (
        "Eagle Ridge JV", "completed", "fast", "Press early")
    assert ok_json(c.get(f"/api/scouting/reports/{b}"))["report"]["opponent_name"] == "Falcon Creek"

    # Pages render.
    for path in ("/scouting", f"/scouting/reports/{a}", f"/scouting/reports/{a}/print"):
        assert c.get(path).status_code == 200, path

    # Delete A: its children are gone, B untouched.
    ok_json(c.delete(f"/api/scouting/reports/{a}"))
    assert c.get(f"/api/scouting/reports/{a}").status_code == 404
    for table in ("scouting_clips", "scouting_personnel", "scouting_offensive_sets", "scouting_practice_points"):
        assert q(app, f"SELECT COUNT(*) AS n FROM {table} WHERE report_id=?", (a,))[0]["n"] == 0, table
    assert [r["id"] for r in ok_json(c.get("/api/scouting/reports"))] == [b]
    assert len(ok_json(c.get(f"/api/scouting/reports/{b}"))["clips"]) == 1


def test_scouting_generate_empty_and_no_game(web, app):
    c = web
    no_game = ok_json(send(c, "post", "/api/scouting/reports", {"opponent_name": "X", "scout_date": "2026-01-01"}), 201)["id"]
    r = c.post(f"/api/scouting/reports/{no_game}/generate")
    assert r.status_code == 400 and "No game" in r.get_json()["error"]
    game = create_game(c, "scout-empty")
    rid = ok_json(send(c, "post", "/api/scouting/reports", {"opponent_name": "Y", "scout_date": "2026-01-01", "game_id": game}), 201)["id"]
    r = c.post(f"/api/scouting/reports/{rid}/generate")
    assert r.status_code == 400 and "No AI events" in r.get_json()["error"]
    assert c.post("/api/scouting/reports/999999/generate").status_code == 404
    assert c.get("/api/scouting/reports/999999").status_code == 404


def test_scouting_generate_uses_trusted_events_only(web, app):
    c = web
    game = create_game(c, "scout-trust")
    save_event(c, game, "Opp Star", "made_two", 1000, status="accepted")
    save_event(c, game, "Ghost Pending", "made_two", 5000, status="pending")
    save_event(c, game, "Ghost Rejected", "turnover", 9000, status="rejected", shot_result=None)
    rid = ok_json(send(c, "post", "/api/scouting/reports", {"opponent_name": "Trust", "scout_date": "2026-01-01", "game_id": game}), 201)["id"]
    out = ok_json(c.post(f"/api/scouting/reports/{rid}/generate"))
    assert out["events_analyzed"] == 1
    assert out["personnel_found"] == 1


def test_scouting_generate_keeps_player_attribution(web, app):
    c = web
    create_player(app, "Liberty Kid", 3)  # players.id == 1
    game = create_game(c, "scout-attr")
    save_event(c, game, "Opp Star", "made_two", 1000)
    save_event(c, game, "1", "turnover", 4000, shot_result=None)  # AI tracker label "1", not players.id 1
    rid = ok_json(send(c, "post", "/api/scouting/reports", {"opponent_name": "Attr", "scout_date": "2026-01-01", "game_id": game}), 201)["id"]
    ok_json(c.post(f"/api/scouting/reports/{rid}/generate"))
    names = sorted(p["player_name"] or f"#{p['jersey_number']}" for p in ok_json(c.get(f"/api/scouting/reports/{rid}/personnel")))
    assert "Liberty Kid" not in names
    assert "Opp Star" in names


def test_scouting_generate_finds_ai_events_by_relational_game(web, app):
    from tests.e2e import data as td

    c = web
    game = create_game(c, "scout-ai")
    conn = raw(app)
    td.insert_ai_events(conn, "scout-ai-video", td.ai_events("scout-ai-video"), relational_game_id=game)
    conn.close()
    assert q(app, "SELECT COUNT(*) AS n FROM events WHERE relational_game_id=?", (game,))[0]["n"] > 0
    # AI drafts are pending; generate only uses trusted events, so a coach accepts the
    # turnovers (legacy events.game_id is the analysis key, not games.id).
    conn = raw(app)
    conn.execute("UPDATE events SET review_status='accepted' WHERE relational_game_id=? AND event_type='turnover'", (game,))
    conn.commit()
    conn.close()
    accepted = q(app, "SELECT COUNT(*) AS n FROM events WHERE relational_game_id=? AND review_status='accepted'", (game,))[0]["n"]
    assert accepted > 0
    assert q(app, "SELECT COUNT(*) AS n FROM events WHERE game_id=?", (str(game),))[0]["n"] == 0
    rid = ok_json(send(c, "post", "/api/scouting/reports", {"opponent_name": "AI", "scout_date": "2026-01-01", "game_id": game}), 201)["id"]
    r = c.post(f"/api/scouting/reports/{rid}/generate")
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["events_analyzed"] == accepted


def test_scouting_child_on_missing_report_is_404(web, app):
    r = send(web, "post", "/api/scouting/reports/424242/clips", {"clip_type": "tendency", "description": "x"})
    assert r.status_code == 404
    r = send(web, "post", "/api/scouting/reports/424242/personnel", {"player_name": "x"})
    assert r.status_code == 404
    assert q(app, "SELECT COUNT(*) AS n FROM scouting_clips WHERE report_id=424242")[0]["n"] == 0


_XSS = "<img src=x onerror=alert(1)>"
_SAFE_TAGS = {"table", "thead", "tbody", "tr", "th", "td", "a", "span", "h1", "h2", "h3", "p", "div",
              "strong", "ul", "li"}


def _render_page_js(client, page_url, target_id, *, call=""):
    """Run the page's own inline scripts (incl. base.html's escapeHtml) under node with the
    real API responses and return the innerHTML the page writes into #target_id."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    html = client.get(page_url).get_data(as_text=True)
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    escape_js = next(sc for sc in scripts if "function escapeHtml(" in sc)
    page_js = next(sc for sc in scripts if "/api/scouting/reports" in sc)
    report_id = re.search(r"const reportId = (\d+);", page_js)
    api = {}
    for url in re.findall(r"fetch\(\s*[`']([^`']+)[`']", page_js):
        if report_id:
            url = url.replace("${reportId}", report_id.group(1))
        api[url] = client.get(url).get_json()
    harness = """
const els = {};
const el = (id) => (els[id] = els[id] || {innerHTML: '', textContent: '', value: '', href: ''});
globalThis.document = {getElementById: el, addEventListener() {}, querySelector: () => ({})};
globalThis.window = {location: {}};
const API = %s;
globalThis.fetch = (url) => Promise.resolve({json: () => Promise.resolve(API[url])});
%s
%s
%s
setTimeout(() => process.stdout.write(JSON.stringify(el(%s).innerHTML)), 50);
""" % (json.dumps(api), escape_js, page_js, call, json.dumps(target_id))
    out = subprocess.run([node, "-e", harness], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _assert_inert(fragment, payloads):
    from html.parser import HTMLParser

    class Collect(HTMLParser):
        def __init__(self):
            super().__init__()
            self.tags, self.attrs, self.text = set(), [], []

        def handle_starttag(self, tag, attrs):
            self.tags.add(tag)
            self.attrs.extend(name for name, _ in attrs)

        def handle_data(self, data):
            self.text.append(data)

    parser = Collect()
    parser.feed(fragment)
    assert parser.tags <= _SAFE_TAGS, parser.tags - _SAFE_TAGS
    assert not [a for a in parser.attrs if a.startswith("on")], parser.attrs
    text = "".join(parser.text)
    for payload in payloads:
        assert payload in text, payload  # shown to the coach as literal text


def test_scouting_pages_escape_stored_text(web):
    c = web
    rid = ok_json(send(c, "post", "/api/scouting/reports", {"opponent_name": _XSS, "scout_date": "2026-01-01"}), 201)["id"]
    ok_json(send(c, "put", f"/api/scouting/reports/{rid}", {"executive_summary": "<b onmouseover=x()>sum</b>"}))
    ok_json(send(c, "post", f"/api/scouting/reports/{rid}/clips", {"clip_type": "t", "description": "<script>x()</script>",
                                                                  "game_time": "<svg onload=x()>"}), 201)
    ok_json(send(c, "post", f"/api/scouting/reports/{rid}/personnel",
                 {"jersey_number": "<i>1</i>", "player_name": "Opp", "role": "r", "notes": "<iframe src=javascript:x()>"}), 201)
    ok_json(send(c, "post", f"/api/scouting/reports/{rid}/offensive-sets", {"set_name": "<u>Horns</u>", "frequency": 1}), 201)
    ok_json(send(c, "post", f"/api/scouting/reports/{rid}/practice-points", {"point_number": 1, "description": "<em>x</em>"}), 201)

    printed = _render_page_js(c, f"/scouting/reports/{rid}/print", "print-report")
    _assert_inert(printed, [_XSS, "<b onmouseover=x()>sum</b>", "<script>x()</script>", "<svg onload=x()>",
                            "<iframe src=javascript:x()>", "<u>Horns</u>", "<em>x</em>"])
    dashboard = _render_page_js(c, "/scouting", "reports-list", call="loadReports();")
    _assert_inert(dashboard, [_XSS])


def test_scouting_module_gate_blocks_when_disabled(web, app):
    c = web
    assert c.get("/api/scouting/reports").status_code == 200
    set_entitlement(app, "scouting", False)
    assert c.get("/api/scouting/reports").status_code == 404
    assert c.get("/scouting").status_code == 404
    assert send(c, "post", "/api/scouting/reports", {"opponent_name": "Z", "scout_date": "2026-01-01"}).status_code == 404
    assert q(app, "SELECT COUNT(*) AS n FROM scouting_reports")[0]["n"] == 0
    set_entitlement(app, "scouting", True)
    assert c.get("/api/scouting/reports").status_code == 200


# ── 2. Practice plans & playlists ────────────────────────────────────────────

def _dev_clip(c, label, start, end, **extra):
    body = {"clip_label": label, "clip_start_ms": start, "clip_end_ms": end, **extra}
    return ok_json(send(c, "post", "/api/clips", body), 201)


def test_practice_plan_and_playlist_journey(web, app):
    c = web
    season = create_season(c, app)
    r = c.post("/practices/save", data={
        "season_id": season, "practice_date": "2026-11-15", "level": "jr_high", "status": "completed",
        "plan_source": "manual", "plan_text": "Shell defense closeouts", "coach_notes": "Talk on switches",
    })
    assert r.status_code == 302
    pid = q(app, "SELECT id FROM practices")[0]["id"]

    # Plan items out of order.
    items = {}
    for title, mins, order in (("Scrimmage", 20, 3), ("Warmup", 10, 1), ("Shell drill", 15, 2)):
        items[title] = ok_json(send(c, "post", f"/api/practices/{pid}/plan-items",
                                    {"title": title, "duration_min": mins, "sort_order": order}), 201)["id"]
    listed = ok_json(c.get(f"/api/practices/{pid}/plan-items"))
    assert [i["title"] for i in listed] == ["Warmup", "Shell drill", "Scrimmage"]
    assert sum(i["duration_min"] for i in listed) == 45
    assert send(c, "post", f"/api/practices/{pid}/plan-items", {"title": ""}).status_code == 400

    # Reorder: Scrimmage first; edit a duration.
    ok_json(send(c, "put", f"/api/plan-items/{items['Scrimmage']}", {"sort_order": 0}))
    ok_json(send(c, "put", f"/api/plan-items/{items['Warmup']}", {"duration_min": 5}))
    listed = ok_json(c.get(f"/api/practices/{pid}/plan-items"))
    assert [(i["title"], i["duration_min"]) for i in listed] == [("Scrimmage", 20), ("Warmup", 5), ("Shell drill", 15)]
    assert send(c, "put", "/api/plan-items/999999", {"sort_order": 1}).status_code == 404

    # Playlist of dev clips: add out of order, reorder by remove/re-add, remove.
    playlist = ok_json(send(c, "post", "/api/playlists", {"name": "Closeouts", "season_id": season, "status": "active"}), 201)["id"]
    c1 = _dev_clip(c, "Clip one", 0, 1000)["id"]
    c2 = _dev_clip(c, "Clip two", 1000, 2000)["id"]
    c3 = _dev_clip(c, "Clip three", 2000, 3000)["id"]
    for cid, order in ((c1, 2), (c2, 1), (c3, 3)):
        ok_json(send(c, "post", f"/api/playlists/{playlist}/clips", {"clip_id": cid, "sort_order": order}), 201)
    got = ok_json(c.get(f"/api/playlists/{playlist}"))
    assert [x["clip_label"] for x in got["clips"]] == ["Clip two", "Clip one", "Clip three"]
    ok_json(c.delete(f"/api/playlists/{playlist}/clips/{c3}"))
    ok_json(send(c, "post", f"/api/playlists/{playlist}/clips", {"clip_id": c3, "sort_order": 0}), 201)
    assert [x["clip_label"] for x in ok_json(c.get(f"/api/playlists/{playlist}"))["clips"]] == ["Clip three", "Clip two", "Clip one"]
    ok_json(c.delete(f"/api/playlists/{playlist}/clips/{c2}"))
    assert [x["clip_id"] for x in ok_json(c.get(f"/api/playlists/{playlist}"))["clips"]] == [c3, c1]
    # Deleting a dev clip removes it from the playlist.
    ok_json(c.delete(f"/api/clips/{c1}"))
    assert [x["clip_id"] for x in ok_json(c.get(f"/api/playlists/{playlist}"))["clips"]] == [c3]
    assert send(c, "post", f"/api/playlists/{playlist}/clips", {}).status_code == 400
    assert c.get(f"/practice-playlists?view_playlist_id={playlist}").status_code == 200

    # Link the playlist into the plan.
    film = ok_json(send(c, "post", f"/api/practices/{pid}/plan-items",
                        {"title": "Film", "item_type": "playlist", "playlist_id": playlist, "duration_min": 10, "sort_order": 9}), 201)
    listed = ok_json(c.get(f"/api/practices/{pid}/plan-items"))
    assert listed[-1]["playlist_name"] == "Closeouts" and listed[-1]["id"] == film["id"]

    # Delete one item.
    ok_json(c.delete(f"/api/plan-items/{items['Shell drill']}"))
    assert [i["title"] for i in ok_json(c.get(f"/api/practices/{pid}/plan-items"))] == ["Scrimmage", "Warmup", "Film"]

    # Notes generation (heuristic; LLM stubbed unavailable) and report/summary pages.
    assert c.post(f"/practices/{pid}/generate").status_code == 302
    row = q(app, "SELECT ai_notes, combined_summary FROM practices WHERE id=?", (pid,))[0]
    assert row["ai_notes"].startswith("Plan focus: Shell defense closeouts Coach notes: Talk on switches")
    assert "Likely emphasis area: defense." in row["ai_notes"]
    assert row["combined_summary"].startswith("Plan: Shell defense closeouts\nCoach: Talk on switches\nAI: ")
    report = c.get(f"/practices/{pid}/report").get_data(as_text=True)
    assert "Talk on switches" in report
    summary = c.get("/practice-summary").get_data(as_text=True)
    assert "Practices in range: 1. Completed: 1. Cancelled: 0. Coach-note coverage: 1/1." in summary

    # Deleting the practice cascades its plan items; the playlist survives.
    assert c.post(f"/practices/{pid}/delete").status_code == 302
    assert q(app, "SELECT COUNT(*) AS n FROM practice_plan_items WHERE practice_id=?", (pid,))[0]["n"] == 0
    assert ok_json(c.get(f"/api/playlists/{playlist}"))["name"] == "Closeouts"

    # Playlist delete removes its clip links.
    ok_json(c.delete(f"/api/playlists/{playlist}"))
    assert c.get(f"/api/playlists/{playlist}").status_code == 404
    assert q(app, "SELECT COUNT(*) AS n FROM practice_playlist_clips WHERE playlist_id=?", (playlist,))[0]["n"] == 0


def test_practice_pages_render_empty(web):
    for path in ("/practices", "/practice-summary", "/practice-playlists", "/player-development"):
        assert web.get(path).status_code == 200, path
    assert "No practices match the selected range." in web.get("/practice-summary").get_data(as_text=True)
    assert web.get("/practices/999/report").status_code == 404
    assert web.post("/practices/999/generate").status_code == 404
    assert ok_json(web.get("/api/practices/999/plan-items")) == []


def test_delete_playlist_used_by_plan_item(web, app):
    c = web
    season = create_season(c, app)
    c.post("/practices/save", data={"season_id": season, "practice_date": "2026-11-16"})
    pid = q(app, "SELECT id FROM practices")[0]["id"]
    playlist = ok_json(send(c, "post", "/api/playlists", {"name": "Film"}), 201)["id"]
    ok_json(send(c, "post", f"/api/practices/{pid}/plan-items", {"title": "Film", "playlist_id": playlist}), 201)
    r = c.delete(f"/api/playlists/{playlist}")
    assert r.status_code == 200
    assert c.get(f"/api/playlists/{playlist}").status_code == 404
    items = ok_json(c.get(f"/api/practices/{pid}/plan-items"))
    assert [(i["title"], i["playlist_id"]) for i in items] == [("Film", None)]


def test_add_missing_clip_to_playlist_is_client_error(web):
    playlist = ok_json(send(web, "post", "/api/playlists", {"name": "P"}), 201)["id"]
    r = send(web, "post", f"/api/playlists/{playlist}/clips", {"clip_id": 987654})
    assert r.status_code in (400, 404)
    assert "987654" in r.get_json()["error"]
    assert ok_json(web.get(f"/api/playlists/{playlist}"))["clips"] == []


def test_practice_generate_with_llm_configured(web, app, monkeypatch):
    import blueprints.practice as practice_mod
    import helpers

    c = web
    season = create_season(c, app)
    c.post("/practices/save", data={"season_id": season, "practice_date": "2026-11-17", "plan_text": "Shooting"})
    pid = q(app, "SELECT id FROM practices")[0]["id"]
    settings = {"features": {}, "analysis": {}, "ai": {"llm_provider": "ollama", "llm_model": "stub-model"}}
    monkeypatch.setattr(practice_mod, "get_runtime_settings", lambda: settings)
    monkeypatch.setattr(helpers, "list_ollama_models", lambda *a, **k: ["stub-model"])
    monkeypatch.setattr(helpers, "call_ollama", lambda *a, **k: (True, "LLM stub notes."))
    r = c.post(f"/practices/{pid}/generate")
    assert r.status_code == 302
    assert q(app, "SELECT ai_notes FROM practices WHERE id=?", (pid,))[0]["ai_notes"] == "LLM stub notes."


# ── 3. Player development ────────────────────────────────────────────────────

def test_player_development_clips_scoped_to_player_and_game(web, app):
    c = web
    alice = create_player(app, "Alice Dev", 4)
    bob = create_player(app, "Bob Dev", 5)
    g1 = create_game(c, "dev-g1")
    g2 = create_game(c, "dev-g2")
    ev_a = save_event(c, g1, "Alice Dev", "made_two", 1000)
    ev_b = save_event(c, g2, "Bob Dev", "turnover", 2000, shot_result=None)

    ca = _dev_clip(c, "Alice finish", 800, 1400, player_id=alice, game_id=str(g1), event_id=ev_a, clip_category="finishing")
    cb = _dev_clip(c, "Bob turnover", 1800, 2400, player_id=bob, game_id=str(g2), event_id=ev_b, clip_category="ball_security")
    assert (ca["player_name"], ca["relational_game_id"], ca["game_id"]) == ("Alice Dev", g1, str(g1))
    assert (cb["player_name"], cb["relational_game_id"]) == ("Bob Dev", g2)
    canon = q(app, "SELECT game_id, event_id, title FROM clips WHERE id=?", (ca["canonical_clip_id"],))[0]
    assert canon == {"game_id": g1, "event_id": ev_a, "title": "Alice finish"}

    assert [x["clip_label"] for x in ok_json(c.get(f"/api/clips?player_id={alice}"))] == ["Alice finish"]
    assert [x["clip_label"] for x in ok_json(c.get(f"/api/clips?player_id={bob}"))] == ["Bob turnover"]
    assert [x["clip_label"] for x in ok_json(c.get(f"/api/clips?relational_game_id={g1}"))] == ["Alice finish"]
    assert [x["clip_label"] for x in ok_json(c.get(f"/api/clips?game_id={g2}"))] == ["Bob turnover"]
    assert ok_json(c.get(f"/api/clips?player_id={alice}&relational_game_id={g2}")) == []

    # Source-key game ids resolve to the relational game too.
    ck = _dev_clip(c, "Alice by key", 3000, 3600, player_id=alice, game_id="dev-g1")
    assert ck["relational_game_id"] == g1

    page = c.get(f"/player-development?player_id={alice}").get_data(as_text=True)
    rows = re.findall(r"<tr>\s*<td>([^<]*)</td>\s*<td>([^<]*)</td>", page)
    assert sorted(rows) == [("Alice Dev", "Alice by key"), ("Alice Dev", "Alice finish")]

    # Validation.
    assert send(c, "post", "/api/clips", {"clip_label": "bad", "clip_start_ms": 500, "clip_end_ms": 100}).status_code == 400
    assert send(c, "post", "/api/clips", {"clip_label": "bad", "clip_start_ms": 0, "clip_end_ms": 100,
                                          "canonical_clip_id": 99999}).status_code == 400


def test_player_development_clip_move_to_other_game(web, app):
    c = web
    alice = create_player(app, "Alice Move", 4)
    g1 = create_game(c, "move-g1")
    g2 = create_game(c, "move-g2")
    clip = _dev_clip(c, "Alice move", 0, 1000, player_id=alice, game_id=str(g1))
    updated = ok_json(send(c, "put", f"/api/clips/{clip['id']}", {"game_id": str(g2)}))
    assert updated["game_id"] == str(g2)
    assert updated["relational_game_id"] == g2
    assert [x["id"] for x in ok_json(c.get(f"/api/clips?relational_game_id={g2}"))] == [clip["id"]]


# ── 4. Read-only assistant ───────────────────────────────────────────────────

@pytest.fixture
def assistant_game(web, app):
    c = web
    game = create_game(c, "assist-game")
    ids = {
        "a1": save_event(c, game, "Alice", "made_two", 1000),
        "a2": save_event(c, game, "Alice", "made_two", 5000),
        "a3": save_event(c, game, "Alice", "made_three", 9000),
        "a_pending": save_event(c, game, "Alice", "made_three", 13000, status="pending"),
        "a_rejected": save_event(c, game, "Alice", "made_two", 17000, status="rejected"),
        "b1": save_event(c, game, "Bob", "made_two", 21000),
        "b_tov": save_event(c, game, "Bob", "turnover", 25000, shot_result=None),
        "b_tov_pending": save_event(c, game, "Bob", "turnover", 29000, status="pending", shot_result=None),
        "b_tov_rejected": save_event(c, game, "Bob", "turnover", 33000, status="rejected", shot_result=None),
        "b_rejected3": save_event(c, game, "Bob", "made_three", 37000, status="rejected"),
        "ghost": save_event(c, game, "Ghost", "made_three", 41000, status="pending"),
    }
    # Dev clips auto-create canonical clips linked to the events.
    for key, label in (("a3", "Alice three"), ("b_tov", "Bob turnover"), ("a_rejected", "Rejected clip"),
                       ("ghost", "Pending clip")):
        _dev_clip(c, label, 0 if key == "a3" else 100, 500, game_id=str(game), event_id=ids[key])
    return game, ids


def test_assistant_answers_from_trusted_events_only(web, assistant_game):
    c = web
    game, ids = assistant_game

    p = ask(c, "How many points did Alice score?", game, "Alice")
    assert p["answer"] == ("Alice has 7 points on 3/3 FG, 0 assists, 0 rebounds, and 0 turnovers "
                           "(reviewed events only).")
    assert (p["confidence"], p["intent"], p["review_scope"]) == ("proven", "player_stats", "accepted_and_corrected_only")
    assert p["citations"][0]["pts"] == 7 and p["citations"][0]["fga"] == 3

    p = ask(c, "How many points did Bob score?", game, "Bob")
    assert p["answer"].startswith("Bob has 2 points on 1/1 FG")
    assert p["citations"][0]["tov"] == 1

    p = ask(c, "Who scored the most points?", game)
    assert p["answer"] == "Alice leads scoring with 7 points (3/3 FG) from reviewed events."

    p = ask(c, "What are our team stats?", game)
    assert p["answer"] == "Team totals from reviewed events: 9 points, 0 rebounds, 0 assists, 1 turnovers."
    assert p["citations"][0]["points"] == 9

    p = ask(c, "How many turnovers did Bob have?", game, "Bob")
    assert p["answer"] == "Bob has 1 reviewed turnover(s) in this game."
    assert [x["event_id"] for x in p["citations"]] == [ids["b_tov"]]

    p = ask(c, "How many points did Ghost score?", game, "Ghost")
    assert p["confidence"] == "unknown"
    assert p["answer"] == "No reviewed stats found for player matching 'Ghost'."

    p = ask(c, "Show me clips", game)
    assert p["intent"] == "clips"
    assert [x["title"] for x in p["citations"]] == ["Alice three", "Bob turnover"]
    p = ask(c, "Show me clips", game, "Bob")
    assert [x["title"] for x in p["citations"]] == ["Bob turnover"]

    # Unknown game / bad input handled gracefully.
    p = ask(c, "How many points?", 999999)
    assert (p["confidence"], p["answer"]) == ("unknown", "Game '999999' was not found.")
    p = ask(c, "How many points?", "no-such-key")
    assert p["confidence"] == "unknown"
    assert send(c, "post", "/api/assistant/query", {"question": "  ", "game_id": game}).status_code == 400
    assert send(c, "post", "/api/assistant/query", {"question": "points?"}).status_code == 400


def test_assistant_guided_workflow(web, assistant_game):
    c = web
    game, ids = assistant_game
    assert c.get("/assistant").status_code == 200

    games = ok_json(c.get("/api/assistant/workflow/games"))
    row = next(g for g in games["games"] if g["id"] == game)
    assert row["trusted_event_count"] == 5  # a1, a2, a3, b1, b_tov
    assert row["label"] == f"Game #{game} — assist-game"

    players = ok_json(c.get(f"/api/assistant/workflow/games/{game}/players"))
    assert [(p["player"], p["pts"], p["tov"]) for p in players["players"]] == [("Alice", 7, 0), ("Bob", 2, 1)]

    clips = ok_json(c.get(f"/api/assistant/workflow/games/{game}/clips?player=Alice"))
    assert [(x["title"], x["event_id"]) for x in clips["clips"]] == [("Alice three", ids["a3"])]
    clips = ok_json(c.get(f"/api/assistant/workflow/games/{game}/clips"))
    assert [x["title"] for x in clips["clips"]] == ["Alice three", "Bob turnover"]
    assert ok_json(c.get(f"/api/assistant/workflow/games/{game}/clips?player=Nobody"))["clips"] == []

    r = c.get("/api/assistant/workflow/games/999999/players")
    assert r.status_code == 404 and r.get_json()["error"] == "Game '999999' was not found"
    assert c.get("/api/assistant/workflow/games/999999/clips").status_code == 404


def test_assistant_empty_game_and_module_gate(web, app):
    c = web
    game = create_game(c, "assist-empty")
    p = ask(c, "Who scored the most points?", game)
    assert (p["confidence"], p["answer"]) == ("unknown", "No reviewed stats are available for this game yet.")
    assert ok_json(c.get(f"/api/assistant/workflow/games/{game}/players"))["players"] == []
    assert ok_json(c.get(f"/api/assistant/workflow/games/{game}/clips"))["clips"] == []
    set_entitlement(app, "ai_assist", False)
    assert send(c, "post", "/api/assistant/query", {"question": "points", "game_id": game}).status_code == 404
    assert c.get("/assistant").status_code == 404
    assert c.get("/api/assistant/workflow/games").status_code == 404


def test_assistant_player_name_prefers_exact_match(web):
    c = web
    game = create_game(c, "assist-names")
    save_event(c, game, "Al", "made_two", 1000)
    save_event(c, game, "Alice", "made_three", 5000)
    p = ask(c, "How many points did Alice score?", game, "Alice")
    assert p["answer"].startswith("Alice has 3 points")
    assert ask(c, "How many points did Al score?", game, "Al")["answer"].startswith("Al has 2 points")


@pytest.mark.xfail(strict=True, reason="BUG: review 'correct' updates event_type text but not event_type_id, so trusted stats/assistant keep the old type")
def test_assistant_reflects_corrected_event_type(web):
    c = web
    game = create_game(c, "assist-correct")
    eid = save_event(c, game, "Carl", "made_two", 1000, status="pending")
    ok_json(send(c, "post", f"/api/review/events/{eid}/correct", {"event_type": "made_three", "notes": "was a three"}))
    p = ask(c, "How many points did Carl score?", game, "Carl")
    assert p["answer"].startswith("Carl has 3 points")


# ── 5. Status and preview pages ──────────────────────────────────────────────

def _num(html, pattern):
    m = re.search(pattern, html, re.S)
    assert m, pattern
    return int(m.group(1))


def test_status_and_preview_pages_with_and_without_data(web, app):
    c = web
    status = c.get("/status")
    assert status.status_code == 200
    s = status.get_data(as_text=True)
    assert "No data yet." in s
    assert "base platform enabled" in s
    assert _num(s, r'status-complete">Accepted</span>\s*<strong>(\d+)</strong>') == 0

    preview = c.get("/preview")
    assert preview.status_code == 200
    p = preview.get_data(as_text=True)
    assert _num(p, r"<strong>(\d+)</strong>\s*<span>Analysis runs</span>") == 0
    assert "Included" in p

    # Add data and turn off the scouting add-on.
    game = create_game(c, "status-game")
    save_event(c, game, "Alice", "made_two", 1000)
    save_event(c, game, "Bob", "made_two", 2000, status="pending")
    save_event(c, game, "Cy", "made_two", 3000, status="rejected")
    c.post("/schedule/seasons/save", data={"name": "S1", "start_date": "2026-11-01", "end_date": "2027-03-01"})
    season = q(app, "SELECT id FROM seasons")[0]["id"]
    c.post("/practices/save", data={"season_id": season, "practice_date": "2026-11-20"})
    set_entitlement(app, "scouting", False)

    s = c.get("/status").get_data(as_text=True)
    assert _num(s, r'status-complete">Accepted</span>\s*<strong>(\d+)</strong>') == 1
    assert _num(s, r'status-in_progress">Pending</span>\s*<strong>(\d+)</strong>') == 1
    assert re.search(r"<code>status-game</code></td>\s*<td>0</td>\s*<td>3</td>", s)
    assert '<span class="entitlement-key disabled">scouting</span>' in s

    p = c.get("/preview").get_data(as_text=True)
    assert _num(p, r"<strong>(\d+)</strong>\s*<span>[^<]*[Pp]ractices?[^<]*</span>") == 1
    card = re.search(r'module-access-badge (\w+)">\s*(?:Included|Not included)\s*</span>\s*<h3>Scouting &amp; Playbook</h3>', p)
    assert card and card.group(1) == "unavailable"
