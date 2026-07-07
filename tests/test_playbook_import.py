"""Playbook import tests."""

import os

import fitz
import pytest


def _write_scout_style_pdf(path):
    """Minimal 2-page PDF matching Fast Scout header layout."""
    doc = fitz.open()
    for page_no, play_name in ((1, "Box 1"), (2, "Cross")):
        page = doc.new_page()
        page.insert_text((72, 72), "21-22 - Liberty Charter Patriots - BLOB - Plays")
        page.insert_text((72, 96), "BLOB")
        page.insert_text((72, 120), play_name)
        for idx, pos in enumerate(["1", "2", "3", "4", "5"], start=1):
            page.insert_text((72, 120 + idx * 18), pos)
    doc.save(path)
    doc.close()


def test_playbook_import_parse_renders_vector_pdf(client, app, tmp_path):
    pdf_path = tmp_path / "scout_sample.pdf"
    _write_scout_style_pdf(str(pdf_path))

    with app.app_context():
        app.config["UPLOAD_FOLDER"] = str(tmp_path)

    with open(pdf_path, "rb") as handle:
        resp = client.post(
            "/playbook/import/parse",
            data={"file": (handle, "scout_sample.pdf")},
            content_type="multipart/form-data",
        )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["page_count"] == 2
    assert payload["recommend_bulk_import"] is True
    assert payload["extracted_images"]
    assert payload["extracted_images"][0]["url"].startswith("/uploads/play_imports/")


def test_bulk_import_parse_groups_scout_pdf(client, app, tmp_path):
    pdf_path = tmp_path / "scout_sample.pdf"
    _write_scout_style_pdf(str(pdf_path))

    with app.app_context():
        app.config["UPLOAD_FOLDER"] = str(tmp_path)

    with open(pdf_path, "rb") as handle:
        resp = client.post(
            "/api/playbook/bulk/parse",
            data={"file": (handle, "scout_sample.pdf")},
            content_type="multipart/form-data",
        )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["total_plays"] == 2
    names = {play["play_name"] for play in payload["plays"]}
    assert names == {"Box 1", "Cross"}
    assert payload["sections"]["BLOB"]["count"] == 2


def test_bulk_import_save_selected_plays(client, app, tmp_path):
    pdf_path = tmp_path / "scout_sample.pdf"
    _write_scout_style_pdf(str(pdf_path))

    with app.app_context():
        from helpers import get_db

        app.config["UPLOAD_FOLDER"] = str(tmp_path)
        db = get_db()
        with open(pdf_path, "rb") as handle:
            parsed = client.post(
                "/api/playbook/bulk/parse",
                data={"file": (handle, "scout_sample.pdf")},
                content_type="multipart/form-data",
            ).get_json()

        save_resp = client.post(
            "/api/playbook/bulk/save",
            json={
                "plays": [
                    {
                        "play_name": parsed["plays"][0]["play_name"],
                        "section": parsed["plays"][0]["section"],
                        "category": "out_of_bounds",
                        "pages": parsed["plays"][0]["pages"],
                    }
                ]
            },
        )
        assert save_resp.status_code == 200
        assert save_resp.get_json()["saved_count"] == 1
        row = db.execute("SELECT name FROM plays WHERE name='Box 1'").fetchone()
        assert row is not None
