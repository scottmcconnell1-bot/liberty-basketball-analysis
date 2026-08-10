"""Tests for sticky play choreography JSON store + API."""

import json
from pathlib import Path

import pytest

from playbook_choreography import (
    CHOREOGRAPHY_VERSION,
    delete_choreography,
    load_choreography,
    save_choreography,
)


class TestChoreographyStore:
    def test_round_trip(self, tmp_path):
        doc = save_choreography(
            98,
            {
                "steps": [
                    {
                        "step_index": 0,
                        "source_image": "/uploads/a.png",
                        "court_frac": {"x": 0.1, "y": 0.2, "w": 0.8, "h": 0.7},
                        "positions": {"o1": {"x": 100.123, "y": 200.456}, "o2": {"x": 300, "y": 210}},
                        "ink": {
                            "paths": {"o1": [{"x": 100, "y": 200}, {"x": 150, "y": 180}]},
                            "marks": {"o1": "cut"},
                            "passes": [{"fromPid": "o1", "toPid": "o2", "type": "pass"}],
                        },
                    }
                ]
            },
            base=tmp_path,
            source="user_save",
        )
        assert doc["version"] == CHOREOGRAPHY_VERSION
        assert doc["sticky"] is True
        assert doc["play_id"] == 98
        assert doc["steps"][0]["positions"]["o1"]["x"] == 100.12

        loaded = load_choreography(98, base=tmp_path)
        assert loaded is not None
        assert loaded["steps"][0]["ink"]["paths"]["o1"][1]["y"] == 180.0
        assert delete_choreography(98, base=tmp_path) is True
        assert load_choreography(98, base=tmp_path) is None

    def test_rejects_empty_steps(self, tmp_path):
        with pytest.raises(ValueError):
            save_choreography(1, {"steps": []}, base=tmp_path)

    def test_strips_defense_tokens(self, tmp_path):
        doc = save_choreography(
            7,
            {
                "steps": [
                    {
                        "positions": {
                            "o1": {"x": 1, "y": 2},
                            "d1": {"x": 9, "y": 9},
                        }
                    }
                ]
            },
            base=tmp_path,
        )
        assert "o1" in doc["steps"][0]["positions"]
        assert "d1" not in doc["steps"][0]["positions"]


class TestChoreographyApi:
    def _make_play(self, db, name="Choreo Test"):
        cur = db.execute(
            "INSERT INTO plays (name, category, diagram_json) VALUES (?, ?, ?)",
            (name, "offense", "{}"),
        )
        db.commit()
        return cur.lastrowid

    def test_get_missing(self, client, db):
        play_id = self._make_play(db)
        r = client.get(f"/api/playbook/choreography/{play_id}")
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert data["sticky"] is False
        assert data["choreography"] is None

    def test_put_get_delete(self, client, db, tmp_path, monkeypatch):
        play_id = self._make_play(db, "Sticky Play")
        # Point choreography base at tmp so tests don't write into repo data/
        from blueprints import playbook as pb

        monkeypatch.setattr(pb, "_choreography_base", lambda: tmp_path)

        payload = {
            "source": "user_save",
            "steps": [
                {
                    "step_index": 0,
                    "source_image": "/uploads/page.png",
                    "positions": {"o1": {"x": 120, "y": 340}, "o5": {"x": 250, "y": 100}},
                    "ink": {
                        "paths": {"o5": [{"x": 250, "y": 100}, {"x": 300, "y": 150}]},
                        "marks": {},
                        "passes": [],
                    },
                }
            ],
        }
        r = client.put(
            f"/api/playbook/choreography/{play_id}",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["sticky"] is True
        assert body["choreography"]["steps"][0]["positions"]["o1"]["x"] == 120.0

        r2 = client.get(f"/api/playbook/choreography/{play_id}")
        assert r2.get_json()["sticky"] is True
        assert Path(tmp_path / "choreography" / f"{play_id}.json").is_file()

        r3 = client.delete(f"/api/playbook/choreography/{play_id}")
        assert r3.status_code == 200
        assert r3.get_json()["deleted"] is True
        assert client.get(f"/api/playbook/choreography/{play_id}").get_json()["sticky"] is False

    def test_404_unknown_play(self, client):
        r = client.get("/api/playbook/choreography/999999")
        assert r.status_code == 404
