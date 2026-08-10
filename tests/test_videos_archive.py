"""Active vs Archive filter for /api/videos (runtime ALTER, no schema.sql)."""


def _insert_video(db, *, stored, opponent, game_id):
    db.execute(
        """INSERT INTO videos
           (original_filename, stored_filename, file_path, file_size_bytes, opponent, game_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (stored, stored, f"uploads/{stored}", 100, opponent, game_id),
    )
    db.commit()
    return db.execute("SELECT id FROM videos WHERE stored_filename=?", (stored,)).fetchone()["id"]


def test_videos_archive_filter_and_toggle(client, db):
    active_id = _insert_video(db, stored="a.mp4", opponent="Alpha", game_id="g_a")
    arch_id = _insert_video(db, stored="z.mp4", opponent="Zebra", game_id="g_z")

    # Default list is active-only (archived=0).
    bare = client.get("/api/videos").get_json()
    assert {row["id"] for row in bare} == {active_id, arch_id}
    assert all(row["archived"] == 0 for row in bare)

    r = client.post(f"/api/videos/{arch_id}/archive")
    assert r.status_code == 200
    body = r.get_json()
    assert body["archived"] == 1
    assert body["archived_at"]

    active = client.get("/api/videos").get_json()
    assert [row["id"] for row in active] == [active_id]

    archived = client.get("/api/videos?archived=1&light=1&sort=title").get_json()
    assert [row["id"] for row in archived] == [arch_id]
    assert archived[0]["archived"] == 1

    counts = client.get("/api/videos/archive-counts").get_json()
    assert counts == {"active": 1, "archived": 1}

    r = client.post(f"/api/videos/{arch_id}/unarchive")
    assert r.status_code == 200
    assert r.get_json()["archived"] == 0

    both = client.get("/api/videos?archived=all").get_json()
    assert {row["id"] for row in both} == {active_id, arch_id}


def test_archive_missing_video_404(client, db):
    assert client.post("/api/videos/99999/archive").status_code == 404
    assert client.post("/api/videos/99999/unarchive").status_code == 404
