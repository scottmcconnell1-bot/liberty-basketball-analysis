"""Tests for FastDraw / sticky playbook possession matching MVP."""


from playbook_choreography import save_choreography
from playbook_play_match import (
    MATCH_VERSION,
    fingerprint_from_choreography_steps,
    fingerprint_from_tracks,
    load_match_results,
    match_possessions_for_game,
    rank_against_library,
    save_match_results,
    score_fingerprints,
)


def _make_play(db, name):
    cur = db.execute(
        "INSERT INTO plays (name, category, diagram_json) VALUES (?, ?, ?)",
        (name, "offense", "{}"),
    )
    db.commit()
    return cur.lastrowid


def _rip_like_steps():
    # Formation: ball high, wing, corner-ish — Rip-ish spacing in court SVG space
    return [
        {
            "step_index": 0,
            "positions": {
                "o1": {"x": 250, "y": 320},
                "o2": {"x": 400, "y": 220},
                "o3": {"x": 100, "y": 220},
                "o4": {"x": 180, "y": 100},
                "o5": {"x": 320, "y": 100},
            },
            "ink": {
                "paths": {
                    "o2": [{"x": 400, "y": 220}, {"x": 280, "y": 160}],
                    "o3": [{"x": 100, "y": 220}, {"x": 200, "y": 180}],
                },
                "marks": {"o2": "cut", "o3": "cut"},
                "passes": [{"fromPid": "o1", "toPid": "o2", "type": "pass"}],
            },
        }
    ]


def _triangle_like_steps():
    return [
        {
            "step_index": 0,
            "positions": {
                "o1": {"x": 250, "y": 280},
                "o2": {"x": 120, "y": 160},
                "o3": {"x": 380, "y": 160},
                "o4": {"x": 200, "y": 80},
                "o5": {"x": 300, "y": 80},
            },
            "ink": {
                "paths": {
                    "o1": [{"x": 250, "y": 280}, {"x": 250, "y": 200}],
                },
                "marks": {"o1": "dribble"},
                "passes": [],
            },
        }
    ]


class TestFingerprintScoring:
    def test_identical_fingerprints_score_high(self):
        steps = _rip_like_steps()
        fp = fingerprint_from_choreography_steps(steps)
        scored = score_fingerprints(fp, fp)
        assert scored["score"] >= 0.85

    def test_distinct_formations_rank_correctly(self):
        rip = fingerprint_from_choreography_steps(_rip_like_steps())
        tri = fingerprint_from_choreography_steps(_triangle_like_steps())
        # Film looks like Rip (scaled pixel cloud matching Rip layout)
        film_tracks = [
            [(250, 320), (250, 300)],
            [(400, 220), (280, 160)],
            [(100, 220), (200, 180)],
            [(180, 100), (180, 110)],
            [(320, 100), (320, 110)],
        ]
        film_fp = fingerprint_from_tracks(film_tracks)
        library = [
            {"play_id": 1, "play_name": "Rip", "fingerprint": rip, "source": "sticky"},
            {"play_id": 2, "play_name": "Triangle", "fingerprint": tri, "source": "sticky"},
        ]
        ranked = rank_against_library(film_fp, library, top_k=2)
        assert ranked[0]["rank"] == 1
        assert ranked[0]["play_name"] == "Rip"
        assert ranked[0]["score"] >= ranked[1]["score"]

    def test_json_side_file_round_trip(self, tmp_path):
        doc = save_match_results(
            "game-abc",
            {
                "library_size": 2,
                "possessions": [
                    {
                        "possession_id": 1,
                        "start_ms": 0,
                        "end_ms": 5000,
                        "suggestions": [
                            {"rank": 1, "play_id": 125, "play_name": "Rip", "score": 0.7}
                        ],
                    }
                ],
            },
            base=tmp_path,
        )
        assert doc["version"] == MATCH_VERSION
        loaded = load_match_results("game-abc", base=tmp_path)
        assert loaded is not None
        assert loaded["possessions"][0]["suggestions"][0]["play_name"] == "Rip"


class TestMatchApi:
    def test_match_possessions_end_to_end(self, app, db, tmp_path):
        rip_id = _make_play(db, "Rip")
        tri_id = _make_play(db, "Triangle")
        save_choreography(rip_id, {"steps": _rip_like_steps()}, base=tmp_path)
        save_choreography(tri_id, {"steps": _triangle_like_steps()}, base=tmp_path)

        game_key = "play-match-game"
        # Person detections approximating Rip formation (pixel space ~ court SVG)
        samples = [
            (0, 250, 320, 1),
            (0, 400, 220, 2),
            (0, 100, 220, 3),
            (0, 180, 100, 4),
            (0, 320, 100, 5),
            (4000, 250, 300, 1),
            (4000, 280, 160, 2),
            (4000, 200, 180, 3),
            (4000, 180, 110, 4),
            (4000, 320, 110, 5),
        ]
        for ts, x, y, tid in samples:
            db.execute(
                """INSERT INTO detections
                   (game_id, frame_number, timestamp_ms, object_class, confidence,
                    x_center, y_center, width, height, tracker_id)
                   VALUES (?, ?, ?, 'person', 0.9, ?, ?, 40, 80, ?)""",
                (game_key, int(ts / 33), ts, x, y, tid),
            )
        db.execute(
            """INSERT INTO events
               (game_id, event_type, timestamp_ms, source_type, confidence, review_status)
               VALUES (?, 'possession_change', 0, 'ai', 0.5, 'pending')""",
            (game_key,),
        )
        db.execute(
            """INSERT INTO events
               (game_id, event_type, timestamp_ms, source_type, confidence, review_status)
               VALUES (?, 'made_two', 5000, 'ai', 0.5, 'pending')""",
            (game_key,),
        )
        db.commit()

        result = match_possessions_for_game(
            db,
            game_key,
            relational_game_id=None,
            choreography_base=tmp_path,
            top_k=3,
            play_ids=[rip_id, tri_id],
        )
        assert result["auto_accept"] is False
        assert result["library_size"] == 2
        assert len(result["possessions"]) >= 1
        top = result["possessions"][0]["suggestions"][0]
        assert top["rank"] == 1
        assert top["play_name"] == "Rip"

    def test_api_get_and_plays_deep_link(self, client, db, tmp_path, monkeypatch):
        from blueprints import ai as ai_bp_mod

        monkeypatch.setattr(ai_bp_mod, "_play_match_store_base", lambda: str(tmp_path / "matches"))
        monkeypatch.setattr(ai_bp_mod, "_choreography_match_base", lambda: str(tmp_path))

        rip_id = _make_play(db, "Rip")
        save_choreography(rip_id, {"steps": _rip_like_steps()}, base=tmp_path)
        game_key = "api-play-match"
        for ts, x, y, tid in [
            (0, 250, 320, 1),
            (0, 400, 220, 2),
            (0, 100, 220, 3),
            (3000, 250, 300, 1),
            (3000, 280, 160, 2),
            (3000, 200, 180, 3),
        ]:
            db.execute(
                """INSERT INTO detections
                   (game_id, frame_number, timestamp_ms, object_class, confidence,
                    x_center, y_center, width, height, tracker_id)
                   VALUES (?, ?, ?, 'person', 0.9, ?, ?, 40, 80, ?)""",
                (game_key, 1, ts, x, y, tid),
            )
        db.execute(
            """INSERT INTO events
               (game_id, event_type, timestamp_ms, source_type, confidence, review_status)
               VALUES (?, 'possession_change', 0, 'ai', 0.5, 'pending')""",
            (game_key,),
        )
        db.execute(
            """INSERT INTO events
               (game_id, event_type, timestamp_ms, source_type, confidence, review_status)
               VALUES (?, 'turnover', 4000, 'ai', 0.5, 'pending')""",
            (game_key,),
        )
        db.commit()

        r = client.get(f"/api/film/{game_key}/play-matches")
        assert r.status_code == 200
        data = r.get_json()
        assert data["auto_accept"] is False
        assert data["version"] == MATCH_VERSION
        assert "possessions" in data

        # Cached read
        r2 = client.get(f"/api/film/{game_key}/play-matches")
        assert r2.status_code == 200
        assert r2.get_json().get("cached") is True

        # Deep link
        r3 = client.get(f"/film/sample.mp4/plays?game_id={game_key}", follow_redirects=False)
        assert r3.status_code in (301, 302)
        assert "plays=1" in (r3.headers.get("Location") or "")

    def test_film_page_includes_play_matches_panel(self, client):
        r = client.get("/film")
        assert r.status_code == 200
        assert b"playMatchesPanel" in r.data
        assert b"Play / set suggestions" in r.data
