"""Ordered end-to-end scenarios. Each step drives the app through its routes exactly as the
UI does, records ids in e.state, and asserts on both the HTTP result and the database.
Used by tests/e2e/test_e2e_flow.py (pytest) and scripts/seed_e2e_data.py (demo data)."""
from __future__ import annotations

import io
import json
import time
import uuid
from pathlib import Path

from tests.e2e import data as td
from tests.e2e.conftest import ok

JSON = "application/json"


def _j(e, method, path, payload, *codes):
    r = getattr(e, method)(path, data=json.dumps(payload), content_type=JSON)
    return ok(r, *(codes or (200, 201)))


# ── 1. every parameterless GET route must not crash ─────────────────────────

def parameterless_get_routes() -> list[str]:
    import app as app_module

    out = []
    for rule in app_module.app.url_map.iter_rules():
        if "GET" in rule.methods and not rule.arguments and rule.endpoint != "static":
            out.append(rule.rule)
    return sorted(set(out))


def sweep_get_routes(e) -> dict:
    results = {}
    for path in parameterless_get_routes():
        if path in ("/logout", "/coach/logout"):
            continue
        r = e.get(path)
        results[path] = r.status_code
    crashes = {p: c for p, c in results.items() if c >= 500}
    assert not crashes, f"500s on: {crashes}"
    e.state["sweep"] = results
    return results


# ── 2. settings / runtime ────────────────────────────────────────────────────

SETTINGS_FORM = {
    "ai_detector_model": "yolov8n.pt", "ai_custom_detector_model": "",
    "ai_ball_detector_model": "models/ball_detector.pt", "ai_custom_ball_detector_model": "",
    "ai_ball_class_id": "0", "ai_ball_confidence": "0.25", "ai_person_confidence": "0.5",
    "ai_inference_device": "auto", "ai_frame_stride": "1", "ai_tracker_max_distance": "80",
    "ai_tracker_max_frame_gap": "5", "ai_llm_provider": "none", "ai_llm_model": "",
}


def feature_form_fields() -> dict:
    """Checkbox fields for every feature flag that is on by default (the settings form posts
    all of them; an omitted checkbox means 'off')."""
    from config import Features

    return {f"feature_{name}": "on" for name in dir(Features)
            if name.startswith("ENABLE_") and getattr(Features, name) is True}


def set_generator_mode(e, mode: str):
    r = e.post("/settings", data={**SETTINGS_FORM, **feature_form_fields(), "ai_event_generator_mode": mode}, follow_redirects=False)
    ok(r, 200, 302, 303)
    conn = e.db()
    row = conn.execute("SELECT value FROM app_settings WHERE key='ai.event_generator_mode'").fetchone()
    conn.close()
    assert row and row[0] == mode, f"settings did not persist mode={mode}: {row}"


def settings_runtime(e):
    rt = e.json("/api/ai/runtime")
    assert "ai_runtime_available" in json.dumps(rt) or isinstance(rt, dict)
    e.json("/api/resource-status")
    ok(e.get("/settings"))
    ok(e.get("/settings/custom-weights"), 200, 302)
    set_generator_mode(e, "expanded")
    e.state["mode"] = "expanded"


# ── 3. seasons + schedule ────────────────────────────────────────────────────

def seasons_and_schedule(e):
    ids = []
    for s in td.seasons():
        r = _j(e, "post", "/api/seasons", s)
        ids.append(r.get_json()["id"] if "id" in (r.get_json() or {}) else None)
    if None in ids:  # fall back to DB lookup
        conn = e.db(); ids = [conn.execute("SELECT id FROM seasons WHERE name=?", (s["name"],)).fetchone()[0] for s in td.seasons()]; conn.close()
    past, cur = ids
    e.state["season_past"], e.state["season_current"] = past, cur
    assert len(e.json("/api/seasons")) >= 2
    _j(e, "put", f"/api/seasons/{cur}", {"name": "E2E Current", "start_date": td.seasons()[1]["start_date"], "end_date": td.seasons()[1]["end_date"]})
    e.json(f"/api/seasons/{cur}")

    game_ids = []
    for g in td.scheduled_games(past, cur):
        r = _j(e, "post", "/api/scheduled_games", g)
        game_ids.append((r.get_json() or {}).get("id"))
    if None in game_ids:
        conn = e.db(); game_ids = [x[0] for x in conn.execute("SELECT id FROM scheduled_games ORDER BY id")]; conn.close()
    e.state["scheduled_games"] = game_ids
    assert len(e.json("/api/scheduled_games")) >= 5
    e.json(f"/api/scheduled_games/{game_ids[0]}")
    _j(e, "put", f"/api/scheduled_games/{game_ids[3]}", {"notes": "updated by e2e", "status": "scheduled"})

    # the HTML form path + result recording
    ok(e.post("/schedule/games/save", data={
        "season_id": cur, "program_name": "Liberty", "team": "jr_boys", "gender": "boys", "level": "jr_high",
        "game_date": "2026-02-02", "game_time": "6:00 PM", "location_type": "home",
        "opponent_name": "Form Opponent", "status": "completed", "notes": "form",
    }, follow_redirects=False), 200, 302, 303)
    conn = e.db(); form_game = conn.execute("SELECT id FROM scheduled_games WHERE opponent_name='Form Opponent'").fetchone()[0]; conn.close()
    ok(e.post(f"/schedule/games/{form_game}/record", data={"liberty_score": "52", "opponent_score": "40", "is_conference": "1"}, follow_redirects=False), 200, 302, 303)
    e.state["form_game"] = form_game
    ok(e.get("/schedule")); ok(e.get(f"/schedule?season_id={cur}"))
    e.json("/api/dashboard"); e.json(f"/api/teams/schedule?season_id={cur}")
    ok(e.get("/schedule/export/maxpreps"), 200, 302)
    e.json("/api/schedule/import-health")

    # PDF import: parse must not crash on a plausible PDF; confirm imports explicit rows
    r = e.post("/api/schedule/import-pdf", data={"pdf": (io.BytesIO(td.schedule_pdf_bytes()), "schedule.pdf"), "team": "jr_boys"}, content_type="multipart/form-data")
    assert r.status_code < 500, r.data[:300]
    r = _j(e, "post", "/api/schedule/import-pdf/confirm", {"team": "jr_boys", "games": [
        {"game_date": "2026-03-03", "game_time": "7:00 PM", "opponent_name": "PDF Import Opp", "location_type": "home", "status": "scheduled", "season_id": cur},
    ]})
    assert (r.get_json() or {}).get("imported", 0) >= 1, r.get_json()
    ok(e.post(f"/schedule/games/{game_ids[4]}/delete", data={}, follow_redirects=False), 200, 302, 303)
    ok(e.post("/schedule/seasons/save", data={"name": "E2E Extra Season", "start_date": "2023-11-01", "end_date": "2024-03-31", "season_type": "regular"}, follow_redirects=False), 200, 302, 303)
    conn = e.db(); extra = conn.execute("SELECT id FROM seasons WHERE name='E2E Extra Season'").fetchone()[0]; conn.close()
    ok(e.post(f"/schedule/seasons/{extra}/delete", data={}, follow_redirects=False), 200, 302, 303)


# ── 4. games / sources / nfhs matches ────────────────────────────────────────

def games_sources_nfhs(e):
    sg = e.state["scheduled_games"][0]
    r = _j(e, "post", "/api/games", {"scheduled_game_id": sg, "source_type": "manual", "source_key": "e2e-game-1",
                                       "home_score": 55, "away_score": 40, "result": "W", "is_conference": 1})
    gid = (r.get_json() or {}).get("id")
    if gid is None:
        conn = e.db(); gid = conn.execute("SELECT id FROM games WHERE source_key='e2e-game-1'").fetchone()[0]; conn.close()
    e.state["game_id"] = gid
    e.json("/api/games"); e.json(f"/api/games/{gid}")
    _j(e, "put", f"/api/games/{gid}", {"home_score": 58, "away_score": 40, "result": "W"})
    ok(e.get("/games"), 200, 302)
    ok(e.post("/games/save", data={"scheduled_game_id": e.state["scheduled_games"][1], "source_type": "manual", "source_key": "e2e-game-2", "home_score": "41", "away_score": "50", "result": "L", "is_conference": "0"}, follow_redirects=False), 200, 302, 303)
    r = _j(e, "post", "/api/sources", {"game_id": gid, "source_type": "file", "source_path": "uploads/e2e_source.mp4"})
    e.json("/api/sources")
    ok(e.post("/games/sources/save", data={"game_id": gid, "source_type": "hudl", "source_path": "https://example.invalid/hudl/1"}, follow_redirects=False), 200, 302, 303)
    r = _j(e, "post", "/api/nfhs_matches", {"scheduled_game_id": e.state["scheduled_games"][2], "nfhs_game_id": "gam-e2e-123", "nfhs_url": "https://www.nfhsnetwork.com/events/e2e/gam-e2e-123", "match_status": "pending", "confidence": 0.8})
    mid = (r.get_json() or {}).get("id")
    if mid is None:
        conn = e.db(); mid = conn.execute("SELECT id FROM nfhs_matches ORDER BY id DESC LIMIT 1").fetchone()[0]; conn.close()
    ok(e.post(f"/api/nfhs_matches/{mid}/confirm", data={}), 200, 302)
    e.json("/api/nfhs_matches"); ok(e.get("/nfhs-matches"))
    ok(e.post("/nfhs-matches/add", data={"scheduled_game_id": e.state["scheduled_games"][3], "nfhs_game_id": "gam-e2e-456", "nfhs_url": "https://www.nfhsnetwork.com/events/e2e/gam-e2e-456", "confidence": "0.5"}, follow_redirects=False), 200, 302, 303)
    ok(e.get(f"/api/four_factors/{gid}"), 200, 404)


# ── 5. rosters / players / team photos ───────────────────────────────────────

def roster_and_players(e):
    r = e.post("/api/rosters/import", data={"file": (io.BytesIO(td.roster_csv_bytes()), "roster.csv"), "file_type": "auto"}, content_type="multipart/form-data")
    ok(r); parsed = r.get_json() or {}
    parsed_players = parsed.get("players") or []
    assert len(parsed_players) >= 12, parsed
    for p in parsed_players:  # the parse endpoint only parses; the UI then creates players
        _j(e, "post", "/api/players", {"name": p.get("name"), "jersey_number": str(p.get("jersey_number") or p.get("jersey") or ""),
                                       "position": p.get("position") or "", "grade": str(p.get("grade") or ""),
                                       "program_name": "Liberty", "gender": "boys", "level": "jr_high", "season_id": e.state["season_current"]})
    players = e.json("/api/players")
    assert len(players) >= 12, len(players)
    r = _j(e, "post", "/api/players", {"name": "Temp Player", "jersey_number": "99", "position": "G", "grade": "8", "program_name": "Liberty", "gender": "boys", "level": "jr_high", "season_id": e.state["season_current"]})
    pid = (r.get_json() or {}).get("id")
    if pid: ok(e.delete(f"/api/players/{pid}"), 200, 204)
    e.state["player_ids"] = [p.get("id") for p in players if isinstance(p, dict)][:5]

    r = e.post("/api/film-rosters/import", data={"file": (io.BytesIO(td.roster_csv_bytes()), "home.csv"), "file_type": "csv", "side": "home", "season_id": str(e.state["season_current"]), "level": "jrhigh", "gender": "boys", "replace": "1"}, content_type="multipart/form-data")
    ok(r)
    r = e.post("/api/film-rosters/import", data={"file": (io.BytesIO(td.roster_csv_bytes(td.OPPONENT_PLAYERS)), "away.csv"), "file_type": "csv", "side": "away", "season_id": str(e.state["season_current"]), "level": "jrhigh", "gender": "boys", "replace": "1"}, content_type="multipart/form-data")
    ok(r)
    e.json(f"/api/film-rosters?season_id={e.state['season_current']}&level=jrhigh&gender=boys&side=home")
    _j(e, "put", "/api/film-rosters", {"side": "away", "replace": True, "season_id": e.state["season_current"], "level": "jrhigh", "gender": "boys",
                                        "players": [{"jersey_number": j, "name": n, "label": f"{j} - {n}"} for _, j, n, _ in td.OPPONENT_PLAYERS]})

    r = e.post("/api/teams/photos/upload", data={"file": (io.BytesIO(td.png_bytes()), "team.png"), "team_key": "jr_boys", "caption": "e2e"}, content_type="multipart/form-data")
    ok(r, 200, 201)
    photos = e.json("/api/teams/photos")
    photo_id = (photos[0] if isinstance(photos, list) and photos else (photos.get("photos") or [{}])[0]).get("id")
    if photo_id: ok(e.delete(f"/api/teams/photos/{photo_id}"), 200, 204)


# ── 6. users / messaging / issues ────────────────────────────────────────────

def users_messaging_issues(e):
    for email, name, role in (("coach.e2e@example.com", "Coach E2E", "coach"), ("admin.e2e@example.com", "Admin E2E", "admin")):
        ok(e.post("/register", data={"email": email, "password": "e2e-password-1", "password2": "e2e-password-1", "display_name": name, "role": role}, follow_redirects=False), 200, 302, 303)
    conn = e.db()
    users = {r["email"]: r["id"] for r in conn.execute("SELECT id, email FROM users")}
    conn.close()
    assert "coach.e2e@example.com" in users and "admin.e2e@example.com" in users
    e.state["users"] = users
    ok(e.post("/login", data={"email": "coach.e2e@example.com", "password": "e2e-password-1"}, follow_redirects=False), 200, 302, 303)
    ok(e.get("/profile"))
    ok(e.post("/profile/edit", data={"display_name": "Coach E2E (edited)", "phone": "555-0100", "avatar_url": ""}, follow_redirects=False), 200, 302, 303)
    ok(e.get("/settings/notifications"))
    ok(e.post("/settings/notifications", data={"notify_email_messages": "1", "notify_push_messages": "0", "quiet_hours_start": "22:00", "quiet_hours_end": "07:00"}, follow_redirects=False), 200, 302, 303)
    e.json("/api/users")
    # ids are strings on the wire (the handler .strip()s them)
    r = _j(e, "post", "/api/messages/send", {"recipient_id": str(users["admin.e2e@example.com"]), "body": "hello from e2e", "sender_id": str(users["coach.e2e@example.com"])})
    convs = e.json("/api/messages/conversations")
    clist = convs if isinstance(convs, list) else convs.get("conversations", [])
    assert clist, convs
    conv_id = clist[0].get("id") or clist[0].get("conversation_id")
    e.json(f"/api/messages/poll?conversation_id={conv_id}")
    conn = e.db(); mids = [r[0] for r in conn.execute("SELECT id FROM messages ORDER BY id DESC LIMIT 1")]; conn.close()
    _j(e, "post", "/api/messages/read", {"message_ids": mids, "user_id": str(users["admin.e2e@example.com"])})
    ok(e.get("/messages"))
    e.json("/api/notifications"); _j(e, "post", "/api/notifications/read", {"ids": []})
    ok(e.get("/api/push/vapid-public-key"), 200, 404, 503)
    ok(e.post("/debug/issues", data={"entry_type": "issue", "title": "E2E issue", "details": "created by the e2e suite", "return_to": "/debug", "source_path": "/e2e"}, follow_redirects=False), 200, 302, 303)
    conn = e.db(); iid = conn.execute("SELECT id FROM issue_reports ORDER BY id DESC LIMIT 1").fetchone()[0]; conn.close()
    ok(e.post(f"/debug/issues/{iid}/complete", data={"return_to": "/debug"}, follow_redirects=False), 200, 302, 303)
    ok(e.get("/debug")); ok(e.get("/users"))
    ok(e.get("/logout"), 200, 302)


# ── 7. video upload (normal + chunked), analysis, trim, archive, rerun ───────

def video_upload(e, real_film: bool = True):
    use_real = real_film and td.has_real_film() and td.ffmpeg_available()
    primary = td.make_real_clip(e.workdir / "e2e_real12.mp4") if use_real else td.make_synthetic_video(e.workdir / "e2e_synth.mp4")
    secondary = td.make_synthetic_video(e.workdir / "e2e_synth2.mp4", seconds=4)
    e.state["primary_video_path"] = str(primary)

    with open(primary, "rb") as fh:
        r = e.post("/upload", data={"video": (fh, primary.name), "opponent": "E2E Opponent"}, content_type="multipart/form-data",
                   headers={"X-Requested-With": "XMLHttpRequest"})
    ok(r); payload = r.get_json(); assert payload["status"] == "uploaded", payload
    game_id = payload["game_id"]; stored = payload["stored_filename"]
    e.state["game_key"], e.state["stored"] = game_id, stored
    conn = e.db(); vid = conn.execute("SELECT id FROM videos WHERE stored_filename=?", (stored,)).fetchone()[0]; conn.close()
    e.state["video_id"] = vid
    assert Path(e.uploads, stored).exists() if e.uploads else True

    prog = e.ensure_analysis(game_id)
    assert prog["status"] == "completed", prog
    conn = e.db()
    e.state["n_detections"] = conn.execute("SELECT COUNT(*) FROM detections WHERE game_id=?", (game_id,)).fetchone()[0]
    e.state["n_events"] = conn.execute("SELECT COUNT(*) FROM events WHERE game_id=?", (game_id,)).fetchone()[0]
    conn.close()
    assert e.state["n_detections"] > 0
    e.json(f"/api/analysis_status/{game_id}")

    # chunked upload of the second clip (3 chunks, no analysis)
    blob = secondary.read_bytes(); n = 3; size = -(-len(blob) // n); upload_id = uuid.uuid4().hex
    last = None
    for i in range(n):
        chunk = blob[i * size:(i + 1) * size]
        last = e.post("/api/upload_chunk", data={"file": (io.BytesIO(chunk), "chunk"), "upload_id": upload_id, "chunk_index": str(i), "total_chunks": str(n), "filename": secondary.name, "opponent": "E2E Chunked", "upload_mode": "upload_only"}, content_type="multipart/form-data")
        ok(last)
    conn = e.db(); vid2 = conn.execute("SELECT id FROM videos WHERE opponent='E2E Chunked'").fetchone(); conn.close()
    assert vid2, f"chunked upload did not create a videos row: {last.get_json()}"
    e.state["video_id_2"] = vid2[0]

    vids = e.json("/api/videos"); assert len(vids if isinstance(vids, list) else vids.get("videos", [])) >= 2
    e.json(f"/api/videos/{vid}"); e.json(f"/api/videos/{vid}/meta"); e.json("/api/videos/archive-counts")
    ok(e.get(f"/api/videos/{vid}/analysis-debug"), 200, 404)
    ok(e.get(f"/api/check_duplicate?filename={primary.name}"))
    ok(e.get("/videos")); ok(e.get(f"/videos/{vid}/trim"))
    ok(e.post(f"/api/videos/{e.state['video_id_2']}/archive", data={})); ok(e.post(f"/api/videos/{e.state['video_id_2']}/unarchive", data={}))

    # trim job (background thread; ffmpeg)
    if td.ffmpeg_available():
        r = _j(e, "post", f"/api/videos/{vid}/trim", {"start_ms": 0, "end_ms": 2000, "label": "e2e trim"}, 200, 202)
        job = (r.get_json() or {}).get("job_id")
        assert job, r.get_json()
        for _ in range(60):
            st = e.json(f"/api/videos/trim/{job}")
            if st["status"] in ("complete", "failed"): break
            time.sleep(1)
        assert st["status"] == "complete", st
        e.state["trim_video_id"] = st.get("video_id")

    ok(e.get(f"/videos/{vid}/compare"))
    ok(e.post(f"/videos/{vid}/rerun", data={"run_label": "E2E rerun"}, follow_redirects=False), 200, 302, 303)
    conn = e.db(); rr = conn.execute("SELECT analysis_key, status FROM analysis_runs WHERE run_kind='rerun' ORDER BY id DESC LIMIT 1").fetchone(); conn.close()
    assert rr, "rerun did not create an analysis_runs row"
    e.state["rerun_key"] = rr[0]
    e.ensure_analysis(rr[0])
    ok(e.get(f"/videos/{vid}/compare"))


# ── 8. analysis pages, events API, manual event round trip ───────────────────

def analysis_pages_and_events(e):
    g, stored = e.state["game_key"], e.state["stored"]
    for p in (f"/analysis/{g}", f"/api/analysis/{g}", f"/api/analysis/{g}/events", f"/api/analysis/{g}/roster",
              f"/api/stats/{g}", f"/api/possessions/{g}", f"/api/court-slots/{g}", f"/api/track-identity/{g}",
              f"/film/{stored}", f"/film/{stored}?game_id={g}", f"/film/{stored}/review?game_id={g}", f"/film/{stored}/plays?game_id={g}",
              f"/api/film/{g}/play-matches", f"/api/events/{g}"):
        ok(e.get(p), 200, 302)
    _j(e, "put", f"/api/court-slots/{g}", {"mappings": [{"tracker_id": 1, "jersey_number": "1", "player_name": "Avery Northwind"},
                                                        {"tracker_id": 2, "jersey_number": "3", "player_name": "Blake Ironwood"}],
                                            "apply_to_events": False}, 200, 400)
    ok(e.post(f"/api/court-slots/{g}/auto-apply", data={}), 200, 400, 409)
    ok(e.post(f"/api/court-slots/{g}/apply", data={}), 200, 400, 409)
    _j(e, "post", f"/api/film/{g}/play-matches/run", {"top_k": 3}, 200, 400, 404)
    # manual events are keyed by the relational games.id (save_event int()s it)
    r = _j(e, "post", "/api/save_event", {"event_type": "shot", "timestamp_ms": 1500, "game_id": e.state["game_id"], "player": "1", "shot_result": "make",
                                          "human_verified": True, "source_type": "manual", "details_json": json.dumps({"note": "e2e manual"})})
    eid = (r.get_json() or {}).get("id") or (r.get_json() or {}).get("event_id")
    if not eid:
        conn = e.db(); eid = conn.execute("SELECT id FROM events ORDER BY id DESC LIMIT 1").fetchone()[0]; conn.close()
    _j(e, "put", f"/api/events/{eid}", {"player": "3", "shot_result": "miss"})
    ok(e.delete(f"/api/events/{eid}"), 200, 204)


# ── 9. review queue -> ledger -> highlights -> clips -> playlists ────────────

def review_and_highlights(e):
    g = e.state["game_key"]
    pending = e.json(f"/api/review/events?game_id={g}&review_status=pending")
    assert len(pending) >= 3, f"expected pending AI drafts, got {len(pending)}"
    shot = next((x for x in pending if x["event_type"] == "shot"), pending[0])
    other = next((x for x in pending if x["id"] != shot["id"] and x["event_type"] != "shot"), pending[1])
    third = next((x for x in pending if x["id"] not in (shot["id"], other["id"])), pending[2])
    _j(e, "post", f"/api/review/events/{shot['id']}/accept", {"notes": "e2e accept"})
    _j(e, "post", f"/api/review/events/{other['id']}/reject", {"notes": "e2e reject"})
    _j(e, "post", f"/api/review/events/{third['id']}/correct", {"event_type": "turnover", "player": "4", "notes": "e2e correct"})
    conn = e.db()
    st = {r[0]: r[1] for r in conn.execute("SELECT id, review_status FROM events WHERE id IN (?,?,?)", (shot["id"], other["id"], third["id"]))}
    conn.close()
    assert st == {shot["id"]: "accepted", other["id"]: "rejected", third["id"]: "corrected"}, st
    e.state["accepted_event"], e.state["corrected_event"] = shot["id"], third["id"]
    ok(e.get("/review")); ok(e.get(f"/review?game_id={g}"))
    for status in ("accepted", "rejected", "corrected", "all"):
        e.json(f"/api/review/events?game_id={g}&review_status={status}")

    e.json("/api/highlights/games")
    moments = e.json(f"/api/highlights/moments?game_id={g}")["moments"]
    assert {m["id"] for m in moments} >= {shot["id"], third["id"]}
    assert all(m["review_status"] in ("accepted", "corrected") for m in moments)
    cut = td.ffmpeg_available()
    r = _j(e, "post", "/api/highlights/generate", {"game_id": g, "event_ids": [shot["id"], third["id"]], "cut_video": cut, "save_clips": True})
    gen = r.get_json(); assert len(gen["saved_clips"]) == 2, gen
    if cut:
        for job in gen["trim_jobs"]:
            for _ in range(90):
                st = e.json(job["status_url"])
                if st["status"] in ("complete", "failed"): break
                time.sleep(1)
            assert st["status"] == "complete", st
    ok(e.get("/highlights")); ok(e.get(f"/highlights?game_id={g}"))

    clips = e.json("/api/clips"); assert len(clips) >= 2
    cid = clips[0]["id"]
    e.json(f"/api/clips/{cid}")
    _j(e, "put", f"/api/clips/{cid}", {"clip_label": "e2e renamed", "notes": "n"})
    r = _j(e, "post", "/api/clips", {"clip_label": "manual e2e clip", "clip_start_ms": 1000, "clip_end_ms": 3000, "game_id": g, "clip_category": "highlight"})
    new_clip = (r.get_json() or {}).get("id")
    if new_clip:
        _j(e, "post", f"/api/clips/{new_clip}/link-canonical", {"canonical_clip_id": gen["saved_clips"][0]["canonical_clip_id"]}, 200, 400, 404)
        ok(e.delete(f"/api/clips/{new_clip}"), 200, 204)
    r = _j(e, "post", "/api/playlists", {"name": "E2E playlist", "season_id": e.state["season_current"], "level": "jr_high", "status": "active"})
    pl = (r.get_json() or {}).get("id"); assert pl, r.get_json()
    e.state["playlist_id"] = pl
    _j(e, "post", f"/api/playlists/{pl}/clips", {"clip_id": cid, "sort_order": 1})
    e.json(f"/api/playlists/{pl}"); e.json("/api/playlists")
    _j(e, "put", f"/api/playlists/{pl}", {"name": "E2E playlist (edited)"})
    ok(e.delete(f"/api/playlists/{pl}/clips/{cid}"), 200, 204)
    _j(e, "post", f"/api/playlists/{pl}/clips", {"clip_id": cid, "sort_order": 1})
    ok(e.get("/player-development")); ok(e.get("/practice-playlists"))


# ── 10. practices ────────────────────────────────────────────────────────────

def practices(e):
    cur = e.state["season_current"]
    for date_, notes in (("2026-02-10", "shell drill"), ("2026-02-12", "press break")):
        ok(e.post("/practices/save", data={"practice_date": date_, "level": "jr_high", "season_id": cur, "status": "planned", "plan_source": "manual", "plan_text": f"Warmup\n{notes}\nScrimmage", "coach_notes": notes}, follow_redirects=False), 200, 302, 303)
    conn = e.db(); pids = [r[0] for r in conn.execute("SELECT id FROM practices ORDER BY id")]; conn.close()
    assert len(pids) >= 2
    p = pids[0]; e.state["practice_id"] = p
    r = _j(e, "post", f"/api/practices/{p}/plan-items", {"title": "Shell drill", "item_type": "drill", "duration_min": 15, "sort_order": 1, "description": "4v4"})
    item = (r.get_json() or {}).get("id")
    _j(e, "post", f"/api/practices/{p}/plan-items", {"title": "Film: E2E playlist", "item_type": "playlist", "playlist_id": e.state.get("playlist_id"), "duration_min": 10, "sort_order": 2})
    items = e.json(f"/api/practices/{p}/plan-items"); assert len(items) >= 2
    if item:
        _j(e, "put", f"/api/plan-items/{item}", {"duration_min": 20})
        ok(e.delete(f"/api/plan-items/{item}"), 200, 204)
    ok(e.post(f"/practices/{p}/generate", data={}, follow_redirects=False), 200, 302, 303)
    ok(e.get(f"/practices/{p}/report")); ok(e.get("/practices")); ok(e.get("/practice-summary"))
    ok(e.post(f"/practices/{pids[1]}/delete", data={}, follow_redirects=False), 200, 302, 303)


# ── 11. playbook ─────────────────────────────────────────────────────────────

DIAGRAM = json.dumps({"players": [{"id": 1, "x": 0.5, "y": 0.7}, {"id": 2, "x": 0.3, "y": 0.5}], "lines": []})
STEPS = json.dumps([{"step_number": 1, "description": "1 dribbles to wing"}, {"step_number": 2, "description": "4 flare screens 2"}])


def playbook(e):
    r = _j(e, "post", "/api/playbook/categories", {"name": "E2E Sets"})
    cat = (r.get_json() or {}).get("id")
    if cat is None:
        conn = e.db(); cat = conn.execute("SELECT id FROM play_categories WHERE name='E2E Sets'").fetchone()[0]; conn.close()
    _j(e, "put", f"/api/playbook/categories/{cat}", {"name": "E2E Sets (renamed)"})
    e.json("/api/playbook/categories")
    ok(e.post("/playbook/save", data={"name": "E2E Horns Flare", "description": "wing entry", "category_id": cat, "tags": "e2e,horns", "diagram_json": DIAGRAM, "steps_json": STEPS, "team_key": "liberty"}, follow_redirects=False), 200, 302, 303)
    conn = e.db(); play = conn.execute("SELECT id FROM plays WHERE name='E2E Horns Flare'").fetchone()[0]; conn.close()
    e.state["play_id"] = play
    for p in ("/playbook", "/playbook/create", f"/playbook/play/{play}", f"/playbook/play/{play}/edit", f"/api/playbook/play/{play}", f"/playbook/export/{play}", "/playbook/import", "/playbook/opponents", "/playbook/bulk_import"):
        ok(e.get(p), 200, 302)
    r = ok(e.post(f"/api/playbook/play/{play}/share", data={}))
    token = (r.get_json() or {}).get("share_token") or (r.get_json() or {}).get("token") or (r.get_json() or {}).get("url", "").rsplit("/", 1)[-1]
    assert token, r.get_json()
    ok(e.get(f"/play/share/{token}"))           # the route that 500'd before the sqlite3.Row fix
    ok(e.get("/play/share/not-a-real-token"), 404)
    ok(e.post(f"/playbook/play/{play}/duplicate", data={}, follow_redirects=False), 200, 302, 303)
    conn = e.db(); dup = conn.execute("SELECT id FROM plays WHERE id != ? ORDER BY id DESC LIMIT 1", (play,)).fetchone()[0]; conn.close()
    _j(e, "post", "/api/playbook/reorder", {"ordered_ids": [dup, play]}, 200, 400)
    _j(e, "post", "/api/playbook/move-category", {"play_ids": [dup], "category_id": cat}, 200, 400)
    ok(e.post(f"/playbook/play/{dup}/progression-move", data={"direction": "up"}, follow_redirects=False), 200, 302, 303, 400)
    _j(e, "post", f"/api/playbook/choreography/{play}", {"source": "e2e", "steps": [{"step": 1, "positions": {"1": [0.5, 0.7]}}]}, 200, 201, 400)
    ok(e.get(f"/api/playbook/choreography/{play}"), 200, 404)
    ok(e.delete(f"/api/playbook/choreography/{play}"), 200, 204, 404)
    ok(e.post(f"/playbook/play/{dup}/copy-to-team", data={"target_team": "opponent"}, follow_redirects=False), 200, 302, 303, 400)
    ok(e.post("/playbook/opponents", data={"name": "E2E Opponent Book", "description": "scouted"}, follow_redirects=False), 200, 302, 303)
    conn = e.db(); opp = conn.execute("SELECT id FROM playbooks ORDER BY id DESC LIMIT 1").fetchone(); conn.close()
    if opp: ok(e.get(f"/playbook/opponents/{opp[0]}"), 200, 302)
    r = e.post("/playbook/import/parse", data={"file": (io.BytesIO(td.playbook_pdf_bytes()), "plays.pdf")}, content_type="multipart/form-data")
    ok(r); parsed = r.get_json(); assert parsed.get("page_count") == 2, parsed
    r = _j(e, "post", "/playbook/import/save", {"name": "E2E Imported Play", "description": "from pdf", "category": "E2E Sets (renamed)", "category_id": str(cat), "tags": "import", "diagram_json": DIAGRAM, "steps_json": STEPS, "team_key": "liberty"}, 200, 201, 302)
    r = e.post("/api/playbook/bulk/parse", data={"file": (io.BytesIO(td.playbook_pdf_bytes()), "bulk.pdf")}, content_type="multipart/form-data")
    ok(r, 200, 400); bulk = r.get_json() or {}
    r = e.post("/api/playbook/bulk/split", data={"file": (io.BytesIO(td.playbook_pdf_bytes()), "bulk.pdf")}, content_type="multipart/form-data")
    ok(r, 200, 400)
    _j(e, "post", "/api/playbook/bulk/save", {"plays": [{"play_name": "E2E Bulk Play", "section": "Offense", "subsection": "Sets", "pages": bulk.get("pages", [])[:1] or [1], "category_id": cat}]}, 200, 201, 400)
    _j(e, "post", "/api/playbook/sheet-align", {"image_url": "/uploads/does-not-exist.png"}, 200, 400, 404)
    ok(e.post(f"/playbook/play/{dup}/delete", data={}, follow_redirects=False), 200, 302, 303)


# ── 12. scouting ─────────────────────────────────────────────────────────────

def scouting(e):
    r = _j(e, "post", "/api/scouting/reports", {"opponent_name": "Eagle Ridge", "scout_date": "2026-02-01", "film_source": "manual", "game_id": e.state.get("game_id")})
    rid = (r.get_json() or {}).get("id")
    if rid is None:
        conn = e.db(); rid = conn.execute("SELECT id FROM scouting_reports ORDER BY id DESC LIMIT 1").fetchone()[0]; conn.close()
    e.state["report_id"] = rid
    e.json("/api/scouting/reports"); e.json(f"/api/scouting/reports/{rid}")
    _j(e, "put", f"/api/scouting/reports/{rid}", {"opponent_name": "Eagle Ridge (edited)"})
    sections = {
        "personnel": {"jersey_number": "21", "player_name": "Opp Charlie", "role": "primary handler", "notes": "left hand", "usage_rate": 28.5, "ppp": 0.95},
        "offensive-sets": {"set_name": "Horns", "trigger_action": "high PnR", "frequency": "often", "ppp": 0.9, "result_vs_pressure": "turnover prone", "notes": "", "clip_timestamps": "0:45,3:10"},
        "defensive-tendencies": {"scheme": "2-3 zone", "pnr_coverage": "drop", "frequency": "mostly", "ppp_allowed": 0.85, "weak_rotations": "weak side", "notes": ""},
        "tendencies": {"tendency_type": "offense", "category": "transition", "description": "run after misses", "frequency": "high", "clip_timestamps": "1:00", "exploitable": True, "practice_drill": "get back"},
        "situational": {"situation": "BLOB", "description": "box set", "frequency": "every time", "ppp": 1.1, "clip_timestamps": "2:00", "notes": ""},
        "mismatches": {"opponent_jersey": "44", "opponent_name": "Opp Echo", "vulnerability": "slow feet", "exploit_action": "drive", "notes": ""},
        "practice-points": {"point_number": 1, "description": "deny #21", "drill_name": "deny drill", "measurable_target": "<5 catches", "clip_timestamps": ""},
        "clips": {"clip_type": "offense", "game_time": "6:32", "quarter": "Q1", "description": "horns entry", "coach_cue": "watch 21", "video_timestamp_ms": 45000, "source": "manual"},
    }
    for sec, payload in sections.items():
        _j(e, "post", f"/api/scouting/reports/{rid}/{sec}", payload, 200, 201)
        e.json(f"/api/scouting/reports/{rid}/{sec}")
    r = ok(e.post(f"/api/scouting/reports/{rid}/generate", data={}), 200, 202, 400)
    if r.status_code == 400:
        assert "AI events" in (r.get_json() or {}).get("error", ""), r.get_json()
    for p in ("/scouting", f"/scouting/reports/{rid}", f"/scouting/reports/{rid}/print"):
        ok(e.get(p))
    e.json("/api/scouting/nfhs/credentials")
    r = e.post("/api/scouting/nfhs/lookup", data=json.dumps({"nfhs_url": "https://www.nfhsnetwork.com/events/e2e/gam-e2e-123"}), content_type=JSON)
    assert r.status_code < 500 or r.get_json() is not None, r.data[:200]   # offline: a clean error, not a crash page
    ok(e.post("/api/scouting/nfhs/download/does-not-exist/cancel", data={}), 200, 404, 409)
    r = _j(e, "post", "/api/scouting/reports", {"opponent_name": "Temp", "scout_date": "2026-02-02", "film_source": "manual"})
    tmp = (r.get_json() or {}).get("id")
    if tmp: ok(e.delete(f"/api/scouting/reports/{tmp}"), 200, 204)


# ── 13. stat books ───────────────────────────────────────────────────────────

def stat_books(e):
    gid = "e2e-scorebook"
    ok(e.get("/stat-books")); ok(e.get("/stat-books/templates/liberty_spiral_scorebook"))
    ok(e.get("/stat-books/templates/liberty_spiral_scorebook/blank-file"), 200, 404)
    ok(e.get("/stat-books/templates/liberty_spiral_scorebook/layout"))
    ok(e.post("/stat-books/sample", data={}, follow_redirects=False), 200, 302, 303)
    scan = td.SCOREBOOK_PNG.read_bytes()
    r = e.post(f"/stat-books/games/{gid}/upload", data={"template_id": "liberty_spiral_scorebook", "scan": (io.BytesIO(scan), "scan.png")}, content_type="multipart/form-data", follow_redirects=False)
    ok(r, 302, 303)
    ok(e.get(f"/stat-books/games/{gid}/review"))
    ok(e.get(f"/stat-books/games/{gid}/image/aligned.png"), 200, 404)
    _j(e, "post", f"/stat-books/games/{gid}/align", {"template_id": "liberty_spiral_scorebook", "corners": [[0, 0], [1200, 0], [1200, 800], [0, 800]]}, 200, 400)
    draft = e.json(f"/stat-books/games/{gid}/draft")
    box = draft.get("box", draft)
    box.update({"home_team": "Liberty", "away_team": "E2E Opp", "final_score_home": 17, "final_score_away": 0,
                "players": [{"jersey": "21", "name": "Avery Northwind", "team": "home", "extras": {"fg2": 3, "fg3": 3}, "fta": 4, "ftm": 2, "pts": 17}]})
    _j(e, "post", f"/stat-books/games/{gid}/draft", {"box": box})
    r = _j(e, "post", f"/stat-books/games/{gid}/confirm", {"box": box, "confirmed_by": "e2e"})
    assert (r.get_json() or {}).get("ok") is True, r.get_json()
    conf = e.json(f"/stat-books/confirmed/{gid}")
    assert conf["confirmed_by"] == "e2e" and conf["game_id"] == gid


# ── 14. assistant ────────────────────────────────────────────────────────────

def assistant(e):
    ok(e.get("/assistant"))
    r = _j(e, "post", "/api/assistant/query", {"question": "How many shots were taken?", "game_id": e.state["game_key"]})
    assert isinstance(r.get_json(), dict)
    games = e.json("/api/assistant/workflow/games")
    glist = games if isinstance(games, list) else games.get("games", [])
    if glist:
        gid = glist[0]["id"]
        e.json(f"/api/assistant/workflow/games/{gid}/players"); e.json(f"/api/assistant/workflow/games/{gid}/clips")


# ── 15. coach portal (shared password) ───────────────────────────────────────

def coach_portal(e):
    ok(e.get("/coach"), 200, 302)
    ok(e.post("/coach/login", data={"password": "wrong"}, follow_redirects=False), 200, 302, 401, 403)
    ok(e.post("/coach/login", data={"password": "e2e-coach-pass"}, follow_redirects=False), 200, 302, 303)
    try:
        ok(e.get("/coach"), 200, 302); ok(e.get("/coach/progress"))
        # coach sessions are read-only: an ops route must be refused
        ok(e.post(f"/api/videos/{e.state['video_id']}/regenerate-events", data={}), 403)
        ok(e.post("/api/admin/reset", data={}), 403)
    finally:
        ok(e.get("/coach/logout"), 200, 302)
    ok(e.post(f"/api/videos/{e.state['video_id']}/archive", data={}))   # ops work again after logout
    ok(e.post(f"/api/videos/{e.state['video_id']}/unarchive", data={}))


# ── 16. rebuild events in both generator modes through the app ───────────────

def regenerate_both_modes(e):
    vid, g = e.state["video_id"], e.state["game_key"]
    counts = {}
    for mode in ("expanded", "precision"):
        set_generator_mode(e, mode)
        r = ok(e.post(f"/api/videos/{vid}/regenerate-events", data={}), 200, 202)
        conn = e.db()
        counts[mode] = conn.execute("SELECT COUNT(*) FROM events WHERE game_id=? AND source_type='ai'", (g,)).fetchone()[0]
        gens = {row[0] for row in conn.execute("SELECT json_extract(details_json,'$.generator') FROM events WHERE game_id=? AND event_type='shot'", (g,))}
        conn.close()
        if mode == "precision" and counts[mode]:
            assert gens <= {"precision", None}, gens
    e.state["regen_counts"] = counts
    assert counts["precision"] <= counts["expanded"] or counts["expanded"] == 0, counts
    set_generator_mode(e, "expanded")  # leave the production default in place (seeded demo DBs too)


# ── 17. admin reset (temporary DB only) ──────────────────────────────────────

def admin_reset(e):
    ok(e.post("/api/admin/reset", data={}), 200, 302)
    conn = e.db()
    assert conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    conn.close()


SCENARIO_STEPS = [settings_runtime, seasons_and_schedule, games_sources_nfhs, roster_and_players, users_messaging_issues,
         video_upload, analysis_pages_and_events, review_and_highlights, practices, playbook, scouting, stat_books,
         assistant, coach_portal, regenerate_both_modes]


def seed_everything(e, real_film: bool = True):
    for step in SCENARIO_STEPS:
        if step is video_upload:
            step(e, real_film=real_film)
        else:
            step(e)
