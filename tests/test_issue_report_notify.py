"""Bug-report admin notification tests."""

from services.notifications import notify_issue_report_created


def _ensure_notifications_table(db):
    db.execute(
        """CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT,
            link TEXT,
            is_read INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    db.commit()


def _insert_user(db, email, role, display_name=None):
    cur = db.execute(
        """INSERT INTO users (email, password_hash, display_name, role, is_active)
           VALUES (?, ?, ?, ?, 1)""",
        (email, "x", display_name or email.split("@")[0], role),
    )
    db.commit()
    return cur.lastrowid


def test_notify_issue_report_creates_rows_for_admins_only(db):
    _ensure_notifications_table(db)
    admin_id = _insert_user(db, "admin_notify@example.com", "admin", "Admin Coach")
    coach_id = _insert_user(db, "coach_notify@example.com", "coach", "Assist Coach")

    n = notify_issue_report_created(
        db,
        report_id=42,
        entry_type="bug",
        title="Play All wrong",
        details="Tokens on header text",
    )
    assert n >= 1

    rows = db.execute(
        "SELECT user_id, type, title, body, link, is_read FROM notifications WHERE type = ?",
        ("issue_report",),
    ).fetchall()
    assert rows
    assert all(r["user_id"] == admin_id for r in rows)
    assert all(r["user_id"] != coach_id for r in rows)
    assert "Bug report" in rows[0]["title"]
    assert "Play All wrong" in rows[0]["title"]
    assert "/debug/issues" in (rows[0]["link"] or "")


def test_create_issue_report_notifies_admins(client, db):
    _ensure_notifications_table(db)
    admin_id = _insert_user(db, "admin_bug@example.com", "admin", "Scott Admin")

    created = client.post(
        "/debug/issues",
        data={
            "entry_type": "bug",
            "title": "Align too slow",
            "details": "Need ready indicator while aligning.",
            "return_to": "/playbook",
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert created.status_code == 200
    payload = created.get_json()
    assert payload["status"] == "ok"
    report_id = payload["report_id"]

    notifs = db.execute(
        "SELECT * FROM notifications WHERE type = ? AND user_id = ?",
        ("issue_report", admin_id),
    ).fetchall()
    assert len(notifs) >= 1
    assert str(report_id) in (notifs[0]["link"] or "") or "issues" in (notifs[0]["link"] or "")
