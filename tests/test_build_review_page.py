"""Tests for scripts/build_review_page.py (the make/miss review page)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import ai_bridge  # noqa: E402
import build_review_page  # noqa: E402

VIDEO_FRAGMENT = re.compile(
    r'<video[^>]*\bsrc="(file:///[^"]*#t=([0-9.]+),([0-9.]+))"'
)


def pred_make_count(tracks_path: Path) -> int:
    """Return how many saved-rule results the AI called a make."""
    rows = json.loads(tracks_path.read_text(encoding="utf-8"))
    times = [r["t"] for r in rows if r.get("hoop") and len(r["hoop"]) == 4]
    score = ai_bridge.run_saved_v6_rule(times, str(tracks_path))
    return sum(1 for result in score["results"] if result["pred"])


def check_page(html: str, expected_rows: int, expected_makes: int) -> None:
    assert len(re.findall(r'<article class="shot-row"', html)) == expected_rows
    fragments = VIDEO_FRAGMENT.findall(html)
    assert len(fragments) == expected_rows
    for _src, start_text, end_text in fragments:
        start = float(start_text)
        end = float(end_text)
        if start == 0.0:
            assert end - start <= 9.0 + 1e-9
        else:
            assert abs((end - start) - 9.0) < 1e-6
    assert len(re.findall(r'class="call make"', html)) == expected_makes


def test_builds_notus_review_page(tmp_path):
    output = tmp_path / "make_miss_review.html"

    build_review_page.build_review_page([build_review_page.NOTUS_FILM], output)

    html = output.read_text(encoding="utf-8")
    check_page(
        html,
        expected_rows=31,
        expected_makes=pred_make_count(build_review_page.NOTUS_TRACKS),
    )


def test_builds_adrian_review_page_when_tracks_present(tmp_path):
    film = build_review_page.adrian_film()
    if film is None:
        pytest.skip("Adrian v6 tracks are not present on this machine")

    output = tmp_path / "make_miss_review.html"

    build_review_page.build_review_page([film], output)

    html = output.read_text(encoding="utf-8")
    check_page(
        html,
        expected_rows=111,
        expected_makes=pred_make_count(film["tracks"]),
    )
