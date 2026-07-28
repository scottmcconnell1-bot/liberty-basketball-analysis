"""Shareable public links for playbook diagrams."""

from __future__ import annotations

import secrets


def generate_share_token() -> str:
    return secrets.token_urlsafe(12)


def ensure_share_token(db, play_id: int) -> str:
    row = db.execute(
        "SELECT id, share_token FROM plays WHERE id = ?",
        (play_id,),
    ).fetchone()
    if not row:
        raise ValueError("Play not found")
    if row["share_token"]:
        return row["share_token"]
    token = generate_share_token()
    db.execute(
        "UPDATE plays SET share_token = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (token, play_id),
    )
    return token


def get_play_by_share_token(db, token: str):
    if not token:
        return None
    return db.execute(
        "SELECT * FROM plays WHERE share_token = ?",
        (token.strip(),),
    ).fetchone()
