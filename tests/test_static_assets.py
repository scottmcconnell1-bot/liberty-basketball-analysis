"""Static front-end contracts that have no browser test harness."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_service_worker_precache_urls_all_resolve(client):
    """cache.addAll() rejects the whole install if any listed URL fails."""
    sw = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")
    block = re.search(r"const OFFLINE_URLS = \[(.*?)\];", sw, re.S).group(1)
    urls = re.findall(r"'([^']+)'", block)
    assert urls
    for url in urls:
        resp = client.get(url, follow_redirects=True)
        assert resp.status_code == 200, url


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_film_tool_playhead_is_converted_to_analysis_time():
    """Events store analysis time; the playhead is review time (analysis + sync offset)."""
    src = (ROOT / "static" / "js" / "film-tool.js").read_text(encoding="utf-8")

    def extract(name):
        match = re.search(rf"function {name}\([^)]*\) \{{.*?\n\}}\n", src, re.S)
        assert match, name
        return match.group(0)

    script = (
        "let filmSyncOffsetMs = 367000;\n"
        "const video = { currentTime: 1000 };\n"
        + extract("eventReviewSeconds")
        + extract("playheadAnalysisMs")
        + "const ms = playheadAnalysisMs();\n"
        "console.log(JSON.stringify({ms, back: eventReviewSeconds({timestamp_ms: ms})}));\n"
    )
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    result = json.loads(out.stdout)
    assert result == {"ms": 633000, "back": 1000}


def test_film_tool_add_and_lists_use_analysis_time():
    src = (ROOT / "static" / "js" / "film-tool.js").read_text(encoding="utf-8")
    assert "timestamp_ms: playheadAnalysisMs()," in src
    assert "timestamp_ms: Math.round((video?.currentTime || 0) * 1000)" not in src
    assert src.count("const around = playheadAnalysisMs();") == 2
