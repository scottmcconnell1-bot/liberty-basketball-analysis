"""Public self-signup is closed; only admins create accounts."""


def test_anonymous_register_redirects_to_login(client):
    resp = client.get("/register", follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert "/login" in (resp.headers.get("Location") or "")


def test_anonymous_register_post_does_not_create_user(client, db):
    before = db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    resp = client.post(
        "/register",
        data={
            "email": "stranger@example.com",
            "password": "password123",
            "password2": "password123",
            "display_name": "Stranger",
            "role": "admin",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    assert "/login" in (resp.headers.get("Location") or "")
    after = db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    assert after == before
    assert db.execute("SELECT id FROM users WHERE email = ?", ("stranger@example.com",)).fetchone() is None
