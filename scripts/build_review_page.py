#!/usr/bin/env python3
"""Build a self-contained make/miss review page for the saved v6 tracks.

Usage:
    .\\.venv\\Scripts\\python.exe scripts/build_review_page.py [--open]
"""
from __future__ import annotations

import argparse
import contextlib
import html
import io
import json
import os
import subprocess
import sys
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import ai_bridge  # noqa: E402
import team_score  # noqa: E402

DEFAULT_OUTPUT = Path(r"C:\Users\scott\Documents\Liberty_Review\make_miss_review.html")
NOTUS_TRACKS = ROOT / "gemini-upload" / "notus_q1_v6_tracks.json"
NOTUS_VIDEO = "LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4"
ADRIAN_VIDEO = "nfhs_gam0a66d85e12.mp4"
UPLOADS_URL = "file:///" + (ROOT / "uploads").as_posix() + "/"

NOTUS_FILM: dict[str, Any] = {
    "key": "notus",
    "label": "Notus A1 Q1",
    "tracks": NOTUS_TRACKS,
    "video": NOTUS_VIDEO,
}


def adrian_film() -> dict[str, Any] | None:
    """Return the Adrian film definition if its tracks are available."""
    tracks = team_score.adrian_tracks_path()
    if tracks is None:
        return None
    return {
        "key": "adrian",
        "label": "Adrian Q1-Q3",
        "tracks": Path(tracks),
        "video": ADRIAN_VIDEO,
    }


def default_films() -> list[dict[str, Any]]:
    """Return every film whose saved tracks are present on this machine."""
    films = [NOTUS_FILM]
    adrian = adrian_film()
    if adrian is not None:
        films.append(adrian)
    return films


def _format_clock(seconds: float) -> str:
    minutes = int(seconds // 60)
    return f"{minutes}:{seconds % 60:04.1f}"


def _score_film(film: dict[str, Any]) -> dict[str, Any]:
    path = Path(film["tracks"])
    with path.open("r", encoding="utf-8") as fh:
        rows = json.load(fh)
    times = [r["t"] for r in rows if r.get("hoop") and len(r["hoop"]) == 4]
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        score = ai_bridge.run_saved_v6_rule(times, str(path))
    return score


def _git_info() -> tuple[str, str]:
    def run(args: list[str]) -> str:
        try:
            result = subprocess.run(
                args,
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        return result.stdout.strip()

    return (
        run(["git", "rev-parse", "--short", "HEAD"]) or "unknown",
        run(["git", "rev-parse", "--abbrev-ref", "HEAD"]) or "unknown",
    )


def _collect(
    films: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    shot_rows: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for film in films:
        score = _score_film(film)
        summaries.append(
            {
                "label": film["label"],
                "rows": len(score["results"]),
                "right": score["right"],
                "total": score["total_tags"],
                "makes_missed": score["makes_missed"],
                "misses_called_makes": score["misses_called_makes"],
            }
        )
        for result in sorted(score["results"], key=lambda r: r["tag_ts"]):
            tag_ts = result["tag_ts"]
            seconds = tag_ts / 1000.0
            start = max(0.0, seconds - 3.0)
            end = seconds + 6.0
            shot_rows.append(
                {
                    "id": f"{film['key']}-{tag_ts}",
                    "film": film["label"],
                    "film_key": film["key"],
                    "tag_ts": tag_ts,
                    "time": _format_clock(seconds),
                    "ai_call": "make" if result["pred"] else "miss",
                    "scott_tag": "make" if result["true"] else "miss",
                    "start": start,
                    "end": end,
                    "src": UPLOADS_URL
                    + film["video"]
                    + f"#t={start:.1f},{end:.1f}",
                }
            )
    return shot_rows, summaries


def _render_row(row: dict[str, Any]) -> str:
    call = html.escape(row["ai_call"])
    call_label = "MAKE" if row["ai_call"] == "make" else "MISS"
    film = html.escape(row["film"])
    row_id = html.escape(row["id"], quote=True)
    src = html.escape(row["src"], quote=True)
    time = html.escape(row["time"])
    tag_label = "MAKE" if row["scott_tag"] == "make" else "MISS"
    return (
        f'<article class="shot-row" id="{row_id}" data-id="{row_id}" '
        f'data-film="{film}" data-tag-ts="{row["tag_ts"]}" '
        f'data-ai="{call}" data-tag="{html.escape(row["scott_tag"])}" data-mark="">\n'
        "  <div class=\"row-top\">\n"
        "    <div class=\"row-meta\">\n"
        f'      <span class="film">{film}</span>\n'
        f'      <span class="row-key">{row_id}</span>\n'
        f'      <span class="clock">{time}</span>\n'
        "    </div>\n"
        f'    <span class="call {call}">{call_label}</span>\n'
        "  </div>\n"
        f'  <video class="clip" controls preload="none" src="{src}"></video>\n'
        "  <div class=\"row-actions\">\n"
        f'    <button type="button" class="replay" data-start="{row["start"]:.1f}">Replay clip</button>\n'
        '    <button type="button" class="mark-btn correct" data-mark="correct">Correct</button>\n'
        '    <button type="button" class="mark-btn incorrect" data-mark="incorrect">Incorrect</button>\n'
        "  </div>\n"
        f'  <input class="note" type="text" placeholder="Note" aria-label="Note for {row_id}">\n'
        '  <div class="tag-line">\n'
        f'    <span>My tag:</span> <span class="scott-tag {html.escape(row["scott_tag"])}">{tag_label}</span>\n'
        "  </div>\n"
        "</article>"
    )


def _render_scores(summaries: list[dict[str, Any]]) -> str:
    cards = []
    for summary in summaries:
        cards.append(
            '<div class="score-card">'
            f'<div class="score-film">{html.escape(summary["label"])}</div>'
            f'<div class="score-main">{summary["right"]} of {summary["total"]} right</div>'
            f'<div class="score-detail">{summary["makes_missed"]} makes missed &middot; '
            f'{summary["misses_called_makes"]} misses called makes</div>'
            "</div>"
        )
    return '\n'.join(cards)


CSS = """
:root {
  color-scheme: light;
  --bg: #f4f6f8;
  --card: #ffffff;
  --ink: #17202a;
  --muted: #617080;
  --line: #d7dee5;
  --make: #137a3d;
  --make-bg: #d8f3e2;
  --miss: #b42318;
  --miss-bg: #fde4e1;
  --accent: #1f5f9e;
  --accent-bg: #e3effa;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  background: var(--bg);
  color: var(--ink);
  font: 16px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
  padding: 16px;
}
header { max-width: 980px; margin: 0 auto 16px; }
h1 { margin: 0 0 4px; font-size: clamp(1.5rem, 4vw, 2.1rem); }
.meta { color: var(--muted); font-size: 0.9rem; }
.scores {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
  margin-top: 12px;
}
.score-card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 10px 12px;
}
.score-film { color: var(--muted); font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.04em; }
.score-main { font-size: 1.15rem; font-weight: 700; margin: 2px 0; }
.score-detail { color: var(--muted); font-size: 0.9rem; }
.controls {
  position: sticky;
  top: 0;
  z-index: 5;
  max-width: 980px;
  margin: 0 auto 14px;
  background: rgba(244, 246, 248, 0.96);
  border-bottom: 1px solid var(--line);
  padding: 10px 0;
}
.filters { display: flex; flex-wrap: wrap; gap: 8px; }
.filter, .replay, .mark-btn, .save, .show-tags {
  min-height: 46px;
  border: 1px solid var(--line);
  background: var(--card);
  color: var(--ink);
  border-radius: 9px;
  padding: 10px 14px;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  touch-action: manipulation;
}
.filter.active { background: var(--accent); border-color: var(--accent); color: #fff; }
.controls-row { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-top: 10px; }
.show-tags-label {
  display: inline-flex; align-items: center; gap: 8px;
  min-height: 46px; padding: 4px 6px; font-weight: 600; cursor: pointer;
}
.show-tags-label input { width: 22px; height: 22px; }
.counts { color: var(--muted); font-size: 0.95rem; }
.save { background: var(--accent); border-color: var(--accent); color: #fff; margin-left: auto; }
main { max-width: 980px; margin: 0 auto; display: grid; gap: 12px; }
.shot-row {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px;
}
.shot-row[data-mark="correct"] { border-color: var(--make); box-shadow: 0 0 0 2px var(--make-bg) inset; }
.shot-row[data-mark="incorrect"] { border-color: var(--miss); box-shadow: 0 0 0 2px var(--miss-bg) inset; }
.row-top { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.row-meta { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; min-width: 0; }
.film { font-weight: 700; }
.row-key { color: var(--muted); font-size: 0.8rem; overflow-wrap: anywhere; }
.clock { color: var(--muted); font-variant-numeric: tabular-nums; }
.call {
  flex: 0 0 auto;
  font-size: 1.35rem;
  font-weight: 800;
  letter-spacing: 0.06em;
  border-radius: 9px;
  padding: 6px 12px;
}
.call.make { color: var(--make); background: var(--make-bg); border: 1px solid var(--make); }
.call.miss { color: var(--miss); background: var(--miss-bg); border: 1px solid var(--miss); }
.clip { display: block; width: 100%; max-height: 420px; margin: 10px 0; background: #000; border-radius: 8px; }
.row-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.mark-btn.correct.active { background: var(--make); border-color: var(--make); color: #fff; }
.mark-btn.incorrect.active { background: var(--miss); border-color: var(--miss); color: #fff; }
.note {
  width: 100%;
  min-height: 46px;
  margin-top: 10px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 9px;
  font: inherit;
}
.tag-line { display: none; margin-top: 10px; color: var(--muted); align-items: center; gap: 8px; }
body.show-tags .tag-line { display: flex; }
.scott-tag { font-weight: 800; padding: 2px 8px; border-radius: 6px; }
.scott-tag.make { color: var(--make); background: var(--make-bg); }
.scott-tag.miss { color: var(--miss); background: var(--miss-bg); }
@media (max-width: 560px) {
  body { padding: 10px; }
  .save { margin-left: 0; width: 100%; }
  .call { font-size: 1.15rem; }
}
"""

JS = """
const ROWS = __ROWS__;
const STORAGE_KEY = "liberty.make_miss_review.__GIT__";
const rowEls = Array.from(document.querySelectorAll(".shot-row"));
const countReviewed = document.getElementById("reviewed-count");
const countCorrect = document.getElementById("correct-count");
const countIncorrect = document.getElementById("incorrect-count");
let currentFilter = "all";
let state = {};

try {
  state = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}") || {};
} catch (err) {
  state = {};
}

function stateFor(id) {
  const entry = state[id];
  return {
    mark: entry && entry.mark ? entry.mark : null,
    note: entry && typeof entry.note === "string" ? entry.note : "",
  };
}

function saveState(id, entry) {
  state[id] = entry;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch (err) {
    /* Storage can be disabled; the page still works for this session. */
  }
}

function applyRow(el) {
  const entry = stateFor(el.dataset.id);
  el.dataset.mark = entry.mark || "";
  el.querySelectorAll(".mark-btn").forEach((btn) => {
    const active = btn.dataset.mark === entry.mark;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-pressed", active ? "true" : "false");
  });
  const note = el.querySelector(".note");
  if (note.value !== entry.note) {
    note.value = entry.note;
  }
}

function matchesFilter(el) {
  const mark = el.dataset.mark;
  if (currentFilter === "unreviewed") return !mark;
  if (currentFilter === "incorrect") return mark === "incorrect";
  if (currentFilter === "disagree") return el.dataset.ai !== el.dataset.tag;
  return true;
}

function applyFilter() {
  rowEls.forEach((el) => {
    el.hidden = !matchesFilter(el);
  });
}

function refresh() {
  let reviewed = 0;
  let correct = 0;
  let incorrect = 0;
  rowEls.forEach((el) => {
    applyRow(el);
    if (el.dataset.mark === "correct") {
      reviewed += 1;
      correct += 1;
    } else if (el.dataset.mark === "incorrect") {
      reviewed += 1;
      incorrect += 1;
    }
  });
  countReviewed.textContent = "Reviewed " + reviewed + " of " + rowEls.length;
  countCorrect.textContent = "Correct " + correct;
  countIncorrect.textContent = "Incorrect " + incorrect;
  applyFilter();
}

document.addEventListener("click", (event) => {
  const filter = event.target.closest(".filter");
  if (filter) {
    currentFilter = filter.dataset.filter;
    document.querySelectorAll(".filter").forEach((btn) => {
      btn.classList.toggle("active", btn === filter);
    });
    applyFilter();
    return;
  }

  const markBtn = event.target.closest(".mark-btn");
  if (markBtn) {
    const row = markBtn.closest(".shot-row");
    const entry = stateFor(row.dataset.id);
    entry.mark = entry.mark === markBtn.dataset.mark ? null : markBtn.dataset.mark;
    saveState(row.dataset.id, entry);
    refresh();
    return;
  }

  const replay = event.target.closest(".replay");
  if (replay) {
    const row = replay.closest(".shot-row");
    const video = row.querySelector("video");
    const start = Number(replay.dataset.start);
    if (!Number.isFinite(start)) return;
    const seekAndPlay = () => {
      try {
        video.currentTime = start;
      } catch (err) {
        /* Ignore seek errors for unsupported local media. */
      }
      const playing = video.play();
      if (playing && typeof playing.catch === "function") {
        playing.catch(() => {});
      }
    };
    if (video.readyState === 0) {
      video.addEventListener("loadedmetadata", seekAndPlay, { once: true });
      video.load();
    } else {
      seekAndPlay();
    }
  }
});

rowEls.forEach((el) => {
  el.querySelector(".note").addEventListener("input", (event) => {
    const entry = stateFor(el.dataset.id);
    entry.note = event.target.value;
    saveState(el.dataset.id, entry);
  });
});

document.getElementById("show-tags").addEventListener("change", (event) => {
  document.body.classList.toggle("show-tags", event.target.checked);
});

function downloadStamp() {
  const now = new Date();
  const pad = (value) => String(value).padStart(2, "0");
  return (
    now.getFullYear() +
    pad(now.getMonth() + 1) +
    pad(now.getDate()) +
    "_" +
    pad(now.getHours()) +
    pad(now.getMinutes())
  );
}

document.getElementById("save-review").addEventListener("click", () => {
  const payload = {
    built: document.body.dataset.built,
    git: document.body.dataset.git,
    rows: ROWS.map((row) => {
      const entry = stateFor(row.id);
      return {
        id: row.id,
        film: row.film,
        tag_ts: row.tag_ts,
        ai_call: row.ai_call,
        scott_tag: row.scott_tag,
        mark: entry.mark || null,
        note: entry.note,
      };
    }),
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "make_miss_review_" + downloadStamp() + ".json";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

refresh();
"""


def _write_page(
    shot_rows: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    output: Path,
) -> Path:
    """Render the page from collected rows and return its path."""
    output.parent.mkdir(parents=True, exist_ok=True)

    git_hash, branch = _git_info()
    built = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rows_json = json.dumps(shot_rows, ensure_ascii=False).replace("</", "<\\/")
    script = (
        JS.replace("__ROWS__", rows_json)
        .replace("__GIT__", git_hash.replace("\\", "\\\\").replace('"', '\\"'))
    )
    body_rows = "\n".join(_render_row(row) for row in shot_rows)
    header = (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>Make/Miss Review</title>\n"
        "<style>\n" + CSS + "\n</style>\n"
        "</head>\n"
        f'<body data-built="{html.escape(built, quote=True)}" '
        f'data-git="{html.escape(git_hash, quote=True)}">\n'
        "<header>\n"
        "<h1>Make/Miss Review</h1>\n"
        f'<div class="meta">Built {html.escape(built)} &middot; '
        f"git {html.escape(git_hash)} on {html.escape(branch)}</div>\n"
        '<div class="scores">\n' + _render_scores(summaries) + "\n</div>\n"
        "</header>\n"
        '<section class="controls" aria-label="Review controls">\n'
        '  <div class="filters">\n'
        '    <button type="button" class="filter active" data-filter="all">All</button>\n'
        '    <button type="button" class="filter" data-filter="unreviewed">Not reviewed</button>\n'
        '    <button type="button" class="filter" data-filter="incorrect">Marked incorrect</button>\n'
        '    <button type="button" class="filter" data-filter="disagree">AI disagrees with my tag</button>\n'
        "  </div>\n"
        '  <div class="controls-row">\n'
        '    <label class="show-tags-label"><input type="checkbox" id="show-tags"> Show my tags</label>\n'
        '    <div class="counts" aria-live="polite">\n'
        '      <span id="reviewed-count">Reviewed 0 of 0</span> &middot; '
        '<span id="correct-count">Correct 0</span> &middot; '
        '<span id="incorrect-count">Incorrect 0</span>\n'
        "    </div>\n"
        '    <button type="button" class="save" id="save-review">Save my review</button>\n'
        "  </div>\n"
        "</section>\n"
        "<main>\n" + body_rows + "\n</main>\n"
        "<script>\n" + script + "\n</script>\n"
        "</body>\n"
        "</html>\n"
    )
    output.write_text(header, encoding="utf-8")
    return output


def build_review_page(
    films: Iterable[dict[str, Any]],
    output_path: str | Path = DEFAULT_OUTPUT,
) -> Path:
    """Write the self-contained review page and return its path."""
    shot_rows, summaries = _collect(films)
    return _write_page(shot_rows, summaries, Path(output_path))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the make/miss review page.")
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the finished page in the default browser.",
    )
    args = parser.parse_args(argv)

    films = default_films()
    shot_rows, summaries = _collect(films)
    output = _write_page(shot_rows, summaries, DEFAULT_OUTPUT)
    print(f"Wrote {output}")
    for summary in summaries:
        print(f"{summary['label']}: {summary['rows']} shot rows")
    print(f"Total: {len(shot_rows)} shot rows")

    if args.open:
        try:
            os.startfile(str(output))
        except AttributeError:
            webbrowser.open(output.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
