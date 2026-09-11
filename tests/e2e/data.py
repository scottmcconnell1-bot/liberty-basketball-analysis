"""Test-data generators for the end-to-end suite and for `scripts/seed_e2e_data.py`.

Everything here is synthetic or derived from repo sample media. Player names are invented
(the real rosters contain minors; never copy them into fixtures).
"""
from __future__ import annotations

import io
import json
import math
import random
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNIPPET = ROOT / "data" / "videos" / "Q1_snippet.mp4"
SCOREBOOK_PNG = ROOT / "data" / "stat_books" / "templates" / "liberty_spiral_scorebook" / "sample_hsb_liberty.png"

PLAYERS = [  # (pos, jersey, name, grade) - fictional
    ("PG", "1", "Avery Northwind", "8"), ("SG", "3", "Blake Ironwood", "8"), ("SF", "5", "Casey Riverbend", "7"),
    ("PF", "10", "Drew Stonefield", "8"), ("C", "11", "Emery Tallpine", "8"), ("G", "12", "Finley Ashgrove", "7"),
    ("G", "15", "Harper Goldleaf", "8"), ("F", "20", "Jordan Redcliff", "7"), ("F", "23", "Kai Silverbrook", "8"),
    ("C", "24", "Logan Whitecap", "8"), ("G", "33", "Morgan Bluehaven", "7"), ("F", "40", "Riley Copperhill", "8"),
]
OPPONENT_PLAYERS = [("G", "2", "Opp Alpha", "8"), ("G", "4", "Opp Bravo", "8"), ("F", "21", "Opp Charlie", "7"),
                    ("F", "30", "Opp Delta", "8"), ("C", "44", "Opp Echo", "8")]


# ── media ────────────────────────────────────────────────────────────────────

def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def has_real_film() -> bool:
    return SNIPPET.exists() and SNIPPET.stat().st_size > 10_000  # not an LFS pointer


def make_synthetic_video(path: Path, seconds: int = 6, size: str = "640x360", fps: int = 30) -> Path:
    """A small H.264 clip (SMPTE test pattern with a moving marker). Detectors find nothing in it,
    which is fine: it exercises upload, storage, trim, and the failure-free 'no detections' path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size={size}:rate={fps}",
        "-t", str(seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path),
    ], check=True)
    return path


def make_real_clip(path: Path, start_sec: int = 30, seconds: int = 12) -> Path:
    """Cut a short clip from the repo's real sample film (Wilder Q1 snippet, LFS)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(start_sec), "-i", str(SNIPPET),
                    "-t", str(seconds), "-c", "copy", str(path)], check=True)
    return path


def png_bytes(width: int = 320, height: int = 240, color=(30, 90, 160)) -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, height), color)
    d = ImageDraw.Draw(img)
    d.ellipse((40, 40, width - 40, height - 40), outline=(255, 255, 255), width=4)
    d.text((10, 10), "LIBERTY E2E", fill=(255, 255, 255))
    buf = io.BytesIO(); img.save(buf, format="PNG"); return buf.getvalue()


def pdf_bytes(pages: list[list[str]], draw_shapes: bool = False) -> bytes:
    """A real PDF (pymupdf) with one text block per page; optional simple diagram shapes."""
    import pymupdf

    doc = pymupdf.open()
    for lines in pages:
        page = doc.new_page(width=612, height=792)
        y = 72
        for line in lines:
            page.insert_text((72, y), line, fontsize=11); y += 16
        if draw_shapes:
            page.draw_circle((300, 500), 18, color=(0, 0, 0), width=1.5)
            page.draw_circle((380, 420), 18, color=(0, 0, 0), width=1.5)
            page.draw_line((300, 500), (380, 420), color=(0, 0, 0), width=1.5)
            page.draw_rect(pymupdf.Rect(150, 300, 470, 700), color=(0, 0, 0), width=1)
    out = doc.tobytes(); doc.close(); return out


def schedule_pdf_bytes(season_label: str = "2025-26") -> bytes:
    rows = ["Liberty Charter Basketball Schedule (%s)" % season_label, "Date  Opponent  Result",
            "12/1  Riverside  W 55-40", "12/8  @ Mountain View  L 41-50", "1/12  Eagle Ridge  ", "1/19  @ Summit  "]
    return pdf_bytes([rows])


def playbook_pdf_bytes() -> bytes:
    return pdf_bytes([["HORNS FLARE", "1 dribbles to wing, 4 flare screens 2"],
                      ["BOX ZIPPER", "5 sets zipper screen for 1, 2 fills"]], draw_shapes=True)


def roster_csv_bytes(players=PLAYERS) -> bytes:
    return ("POS,#,NAME,GRADE\n" + "".join(f"{p},{j},{n},{g}\n" for p, j, n, g in players)).encode()


# ── schedule ─────────────────────────────────────────────────────────────────

def seasons() -> list[dict]:
    today = date.today()
    return [
        {"name": "2024-25 E2E Boys", "start_date": "2024-11-01", "end_date": "2025-03-31", "season_type": "regular"},
        {"name": "E2E Current", "start_date": (today - timedelta(days=60)).isoformat(),
         "end_date": (today + timedelta(days=120)).isoformat(), "season_type": "regular"},
    ]


def scheduled_games(past_season_id: int, current_season_id: int) -> list[dict]:
    today = date.today()
    base = {"program_name": "Liberty", "gender": "boys", "level": "jr_high", "location_type": "home",
            "game_time": "7:00 PM", "tournament_name": "", "notes": "e2e"}
    return [
        {**base, "season_id": past_season_id, "game_date": "2025-01-10", "opponent_name": "Riverside", "status": "completed"},
        {**base, "season_id": past_season_id, "game_date": "2025-01-17", "opponent_name": "Mountain View", "status": "completed", "location_type": "away"},
        {**base, "season_id": current_season_id, "game_date": (today - timedelta(days=7)).isoformat(), "opponent_name": "Eagle Ridge", "status": "completed"},
        {**base, "season_id": current_season_id, "game_date": (today + timedelta(days=5)).isoformat(), "opponent_name": "Summit", "status": "scheduled"},
        {**base, "season_id": current_season_id, "game_date": (today + timedelta(days=12)).isoformat(), "opponent_name": "Harbor", "status": "scheduled", "location_type": "away"},
    ]


# ── detections + AI events (for when the real detector is not run) ───────────

def synthetic_detections(game_id: str, frames: int = 300, fps: int = 30, width: int = 1280, height: int = 720,
                         seed: int = 7) -> list[dict]:
    """Ten 'players' in stable court positions with jitter, one ball that follows a possessor and
    launches an arc every ~4 s. Enough structure for the event generators to run end to end."""
    rng = random.Random(seed)
    homes = [(200 + (i % 5) * 200, 250 + (i // 5) * 250) for i in range(10)]
    rows = []
    for f in range(frames):
        ts = int(f * 1000 / fps)
        for tid, (hx, hy) in enumerate(homes, start=1):
            rows.append({"frame_number": f, "timestamp_ms": ts, "object_class": "person", "confidence": 0.85,
                         "x_center": hx + rng.uniform(-12, 12), "y_center": hy + rng.uniform(-8, 8),
                         "width": 60, "height": 140, "tracker_id": tid})
        possessor = (f // 120) % 10
        phase = f % 120
        px, py = homes[possessor]
        if phase < 90:
            bx, by = px + 30, py + 40
        else:  # arc toward the top of the frame (the basket) and back
            t = (phase - 90) / 30.0
            bx, by = px + 30 + t * 250, py + 40 - math.sin(t * math.pi) * 320
        if rng.random() < 0.75:  # the real detector misses the ball often; mimic that
            rows.append({"frame_number": f, "timestamp_ms": ts, "object_class": "ball", "confidence": 0.45,
                         "x_center": bx, "y_center": max(20.0, by), "width": 22, "height": 22, "tracker_id": None})
    return rows


def insert_detections(conn, game_id: str, rows: list[dict]) -> int:
    conn.executemany(
        """INSERT INTO detections (game_id, frame_number, timestamp_ms, object_class, confidence,
                                   x_center, y_center, width, height, tracker_id)
           VALUES (:game_id, :frame_number, :timestamp_ms, :object_class, :confidence,
                   :x_center, :y_center, :width, :height, :tracker_id)""",
        [{**r, "game_id": game_id} for r in rows],
    )
    conn.commit()
    return len(rows)


def ai_events(game_id: str) -> list[dict]:
    """Pending AI drafts in the shape event_generator.persist_events expects."""
    import sys
    sys.path.insert(0, str(ROOT))
    from event_generator import make_event

    ev = []
    t = 2000
    for i in range(8):
        shooter = str(1 + i % 5)
        result = "make" if i % 3 else "miss"
        ev.append(make_event(game_id, "shot", t, player=shooter, shot_result=result, confidence=0.6,
                             details={"ball_rise": 120.0, "lateral_travel": 200.0, "peak_frame": t // 33}))
        ev.append(make_event(game_id, result, t, player=shooter, confidence=0.55, details={"derived_from": "shot"}))
        if result == "miss":
            ev.append(make_event(game_id, "rebound", t + 900, player=str(6 + i % 4), confidence=0.5))
        else:
            ev.append(make_event(game_id, "assist", t, player=str(6 + i % 4), confidence=0.4))
        ev.append(make_event(game_id, "possession_change", t + 2500, player=str(6 + i % 4), confidence=0.6))
        if i % 4 == 0:
            ev.append(make_event(game_id, "turnover", t + 2600, player=shooter, confidence=0.45))
            ev.append(make_event(game_id, "steal", t + 2600, player=str(6 + i % 4), confidence=0.45))
        t += 4000
    return ev


def insert_ai_events(conn, game_id: str, events: list[dict], relational_game_id=None) -> int:
    import sys
    sys.path.insert(0, str(ROOT))
    from event_generator import persist_events

    persist_events(conn, game_id, events, relational_game_id=relational_game_id)
    return len(events)


def mark_run_completed(conn, analysis_key: str, detections: int, events: int) -> None:
    conn.execute(
        """UPDATE analysis_runs SET status='completed', progress_pct=100, progress_step='Done',
           completed_at=CURRENT_TIMESTAMP WHERE analysis_key=?""", (analysis_key,))
    conn.commit()


def dumps(obj) -> str:
    return json.dumps(obj)
