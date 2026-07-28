#!/usr/bin/env python3
"""Import HUDL full-game videos + All-Athletes averages CSVs into Liberty.

Source (default): C:\\Users\\scott\\Documents\\HUDL

HUDL CSVs are team / by-period averages (FGM/A, 2PT, 3PT, FT, AST, TO, STL,
BLK, REB, FOUL, points). They have NO Video Time / play-by-play, so they teach
via box-score caps (same role as MaxPreps), not event timestamps.

Videos are hardlinked into uploads/ when possible.

Usage:
  py -3.12 scripts/import_hudl.py
  py -3.12 scripts/import_hudl.py --dry-run
  py -3.12 scripts/import_hudl.py --write-boxscore-model
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from boxscore_constraints import (  # noqa: E402
    DEFAULT_BOXSCORE_MODEL,
    empty_caps,
    load_boxscore_model,
)

DEFAULT_SOURCE = Path(r"C:\Users\scott\Documents\HUDL")
DB_PATH = ROOT / "film_analysis.db"
UPLOADS = ROOT / "uploads"
OUT_DIR = ROOT / "data" / "hudl"

# Filename token → display opponent
ALIAS = {
    "adrian": "Adrian, OR",
    "adrian, or": "Adrian, OR",
    "carey": "Carey",
    "cb": "Centennial Baptist",
    "centennial baptist": "Centennial Baptist",
    "cascade": "Cascade",
    "cvchs": "Cole Valley",
    "cole valley": "Cole Valley",
    "dietrich": "Dietrich",
    "gem state": "Gem State",
    "gsa": "Gem State",
    "gfa": "Greenleaf",  # Greenleaf Friends Academy
    "greenleaf": "Greenleaf",
    "greeleaf": "Greenleaf",  # typo in filename
    "glenns ferry": "Glenns Ferry",
    "horseshoe bend": "Horseshoe Bend",
    "idaho city": "Idaho City",
    "kamiah": "Kamiah",
    "marsing": "Marsing",
    "murtaugh": "Murtaugh",
    "north star": "North Star Charter",
    "nsc": "North Star Charter",
    "raft river": "Raft River",
    "rimrock": "Rimrock",
    "riverstone": "Riverstone",
    "wilder": "Wilder",
    "vale": "Vale",
    "victory": "Victory Charter",
    "victory charter": "Victory Charter",
    "vision charter": "Vision Charter",
    "vision  charter": "Vision Charter",
    "council": "Council",
    "crane": "Crane",
    "crane union": "Crane Union",
    "notus": "Notus",
    "new plymouth (jv)": "New Plymouth (JV)",
    "new plymouth": "New Plymouth (JV)",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(text or "").lower()).strip("_")
    return s or "unknown"


def _norm(text: str) -> str:
    t = str(text or "").lower().replace("&", " and ")
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s*\(\d+\)\s*$", "", t)  # "Averages (1)"
    return t


def resolve_opponent(raw: str) -> str:
    key = _norm(raw)
    if key in ALIAS:
        return ALIAS[key]
    # strip trailing junk
    key2 = re.sub(r"\s*-\d+$", "", key).strip()
    if key2 in ALIAS:
        return ALIAS[key2]
    return raw.strip() or "Unknown"


def parse_video_stem(stem: str) -> dict | None:
    """Return {opponent, location, kind} from an mp4 base name."""
    name = stem.strip()
    # Drop trailing -NNN from some exports
    name = re.sub(r"-\d{2,3}$", "", name).strip()
    low = name.lower()

    kind = "regular"
    if low.startswith("district -"):
        kind = "district"
        opp = name.split("-", 1)[1].strip()
        return {"opponent": resolve_opponent(opp), "location": "neutral", "kind": kind, "raw": stem}
    if low.startswith("state -"):
        kind = "state"
        opp = name.split("-", 1)[1].strip()
        return {"opponent": resolve_opponent(opp), "location": "neutral", "kind": kind, "raw": stem}

    if low.startswith("@ ") or low.startswith("@"):
        opp = name.lstrip("@").strip()
        return {"opponent": resolve_opponent(opp), "location": "away", "kind": kind, "raw": stem}
    if low.startswith("vs ") or low.startswith("vs."):
        opp = re.sub(r"^vs\.?\s*", "", name, flags=re.I).strip()
        return {"opponent": resolve_opponent(opp), "location": "home", "kind": kind, "raw": stem}

    # Bare opponent name (e.g. Raft River.mp4, Victory.mp4)
    return {"opponent": resolve_opponent(name), "location": "unknown", "kind": kind, "raw": stem}


def parse_csv_stem(stem: str) -> dict | None:
    """Parse 'LCHS @ Marsing - All Athletes - Averages' style names."""
    # HUDL exports often use en/em dashes instead of ASCII hyphens.
    name = str(stem or "")
    name = name.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
    name = re.sub(r"\s*\(\d+\)\s*$", "", name).strip()
    name = re.sub(r"\s*-\s*All Athletes\s*-\s*Averages\s*$", "", name, flags=re.I).strip()
    m = re.match(r"^LCHS\s+(@|vs\.?)\s+(.+)$", name, flags=re.I)
    if not m:
        return None
    loc = "away" if m.group(1).startswith("@") else "home"
    return {"opponent": resolve_opponent(m.group(2)), "location": loc, "raw": stem}


def _to_int(val) -> int:
    try:
        s = str(val or "0").replace(",", "").strip()
        if s in {"", "-", "—", "N/A"}:
            return 0
        if s.endswith("%"):
            return 0
        return int(float(s))
    except (TypeError, ValueError):
        return 0


def parse_hudl_averages_csv(path: Path) -> dict | None:
    """Parse Overall team row into box-score style caps + metadata."""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    # Some files quote the title line; normalize to plain CSV rows.
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 3:
        return None

    # Find header that starts with Games,
    header_idx = None
    for i, ln in enumerate(lines):
        if ln.lstrip('"').startswith("Games,"):
            header_idx = i
            break
    if header_idx is None:
        return None

    reader = csv.DictReader(lines[header_idx:])
    overall = None
    periods = {}
    for row in reader:
        games = str(row.get("Games") or "").strip()
        if games == "Overall":
            overall = row
        elif games in {"1st", "2nd", "3rd", "4th", "OT", "OT1", "OT2"}:
            periods[games] = row
        elif games in {"By Period", "0"}:
            continue

    if not overall:
        return None

    # DictReader may get duplicate column names ("0", "eFG%") — csv keeps last.
    # Prefer explicit keys we care about.
    twopm = _to_int(overall.get("2FGM"))
    twopa = _to_int(overall.get("2FGA"))
    threepm = _to_int(overall.get("3FGM"))
    threepa = _to_int(overall.get("3FGA"))
    ftm = _to_int(overall.get("FTM"))
    fta = _to_int(overall.get("FTA"))
    team = empty_caps()
    team.update(
        {
            "2pt_make": twopm,
            "2pt_miss": max(0, twopa - twopm),
            "3pt_make": threepm,
            "3pt_miss": max(0, threepa - threepm),
            "ft_make": ftm,
            "ft_miss": max(0, fta - ftm),
            "reb": _to_int(overall.get("REB")),
            "oreb": _to_int(overall.get("OREB")),
            "dreb": _to_int(overall.get("DREB")),
            "ast": _to_int(overall.get("AST")),
            "stl": _to_int(overall.get("STL")),
            "blk": _to_int(overall.get("BLK")),
            "to": _to_int(overall.get("TO")),
            "pf": _to_int(overall.get("FOUL")),
            "points": _to_int(overall.get("PF")),  # HUDL PF = points for
            "points_against": _to_int(overall.get("PA")),
        }
    )

    period_caps = {}
    for label, row in periods.items():
        twopm = _to_int(row.get("2FGM"))
        twopa = _to_int(row.get("2FGA"))
        threepm = _to_int(row.get("3FGM"))
        threepa = _to_int(row.get("3FGA"))
        ftm = _to_int(row.get("FTM"))
        fta = _to_int(row.get("FTA"))
        period_caps[label] = {
            "2pt_make": twopm,
            "2pt_miss": max(0, twopa - twopm),
            "3pt_make": threepm,
            "3pt_miss": max(0, threepa - threepm),
            "ft_make": ftm,
            "ft_miss": max(0, fta - ftm),
            "reb": _to_int(row.get("REB")),
            "ast": _to_int(row.get("AST")),
            "stl": _to_int(row.get("STL")),
            "blk": _to_int(row.get("BLK")),
            "to": _to_int(row.get("TO")),
            "pf": _to_int(row.get("FOUL")),
            "points": _to_int(row.get("PF")),
            "points_against": _to_int(row.get("PA")),
        }

    return {
        "source": "hudl_averages",
        "source_file": path.name,
        "team_token": "Liberty",
        "players": [],  # team-only export
        "team_totals": team,
        "by_period": period_caps,
        # Shape expected by reference_to_game_caps fallback paths:
        "twopm": team["2pt_make"],
        "twopa": team["2pt_make"] + team["2pt_miss"],
        "threepm": team["3pt_make"],
        "threepa": team["3pt_make"] + team["3pt_miss"],
        "ftm": team["ft_make"],
        "fta": team["ft_make"] + team["ft_miss"],
    }


def match_key(opponent: str, location: str, kind: str = "regular") -> str:
    return f"{kind}|{location}|{_slug(opponent)}"


def discover(source: Path) -> dict:
    videos = []
    for p in sorted(source.glob("*.mp4")):
        meta = parse_video_stem(p.stem)
        if not meta:
            continue
        videos.append({**meta, "path": p})

    csvs = []
    for p in sorted(source.glob("*.csv")):
        meta = parse_csv_stem(p.stem)
        if not meta:
            continue
        csvs.append({**meta, "path": p})

    # Index CSVs by opponent+location; also by opponent alone for fuzzy.
    by_ol: dict[str, list] = {}
    by_opp: dict[str, list] = {}
    for c in csvs:
        ol = f"{c['location']}|{_slug(c['opponent'])}"
        by_ol.setdefault(ol, []).append(c)
        by_opp.setdefault(_slug(c["opponent"]), []).append(c)

    paired = []
    used_csv = set()
    unmatched_videos = []
    for v in videos:
        ol = f"{v['location']}|{_slug(v['opponent'])}"
        candidates = list(by_ol.get(ol) or [])
        # Regular games with unknown location may use any unused opponent CSV.
        # District/State keep location-specific only (avoid wrong-game caps).
        if not candidates and v["location"] == "unknown" and v["kind"] == "regular":
            candidates = list(by_opp.get(_slug(v["opponent"])) or [])
        chosen = None
        for c in candidates:
            if id(c) not in used_csv:
                chosen = c
                break
        game_id = f"hudl_{_slug(v['opponent'])}_{v['location']}_{_slug(v['kind'])}_{_slug(v['raw'])[:40]}"
        film_id = f"hudl-{_slug(v['opponent'])}-{v['location']}-{_slug(v['raw'])[:30]}"
        if chosen is None:
            unmatched_videos.append(v)
            paired.append(
                {
                    "video": v,
                    "csv": None,
                    "game_id": game_id,
                    "film_id": film_id,
                }
            )
            continue
        used_csv.add(id(chosen))
        paired.append(
            {
                "video": v,
                "csv": chosen,
                "game_id": game_id,
                "film_id": film_id,
            }
        )

    unmatched_csvs = [c for c in csvs if id(c) not in used_csv]
    return {
        "paired": paired,
        "unmatched_videos": unmatched_videos,
        "unmatched_csvs": unmatched_csvs,
        "video_count": len(videos),
        "csv_count": len(csvs),
    }


def link_or_copy(src: Path, dest: Path, force_copy: bool = False) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        if dest.stat().st_size == src.stat().st_size:
            return "exists"
        dest.unlink()
    if force_copy:
        shutil.copy2(src, dest)
        return "copied"
    try:
        os.link(src, dest)
        return "hardlink"
    except OSError:
        pass
    try:
        os.symlink(src, dest)
        return "symlink"
    except OSError:
        pass
    shutil.copy2(src, dest)
    return "copied"


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_filename TEXT NOT NULL,
            stored_filename TEXT NOT NULL UNIQUE,
            file_path TEXT NOT NULL,
            file_size_bytes INTEGER,
            opponent TEXT,
            game_id TEXT,
            upload_timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            is_duplicate INTEGER NOT NULL DEFAULT 0,
            duplicate_of_id INTEGER,
            relational_game_id INTEGER
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS film_tool_games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_game_id TEXT NOT NULL UNIQUE,
            analysis_key TEXT,
            relational_game_id INTEGER,
            game_type TEXT,
            game_date TEXT,
            our_team TEXT,
            opponent TEXT,
            tag_count INTEGER DEFAULT 0,
            state_json TEXT,
            created_by_user_id INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    )


def upsert_video(conn, *, stored, original, path, opponent, game_id) -> int:
    row = conn.execute(
        "SELECT id FROM videos WHERE stored_filename = ? OR game_id = ?",
        (stored, game_id),
    ).fetchone()
    size = path.stat().st_size
    if row:
        conn.execute(
            """UPDATE videos SET original_filename=?, stored_filename=?, file_path=?,
                   file_size_bytes=?, opponent=?, game_id=? WHERE id=?""",
            (original, stored, str(path), size, opponent, game_id, row[0]),
        )
        return int(row[0])
    cur = conn.execute(
        """INSERT INTO videos (original_filename, stored_filename, file_path, file_size_bytes,
                               opponent, game_id, is_duplicate)
           VALUES (?,?,?,?,?,?,0)""",
        (original, stored, str(path), size, opponent, game_id),
    )
    return int(cur.lastrowid)


def upsert_film_tool(conn, payload: dict) -> None:
    client_id = payload["id"]
    state_json = json.dumps(payload, ensure_ascii=False)
    existing = conn.execute(
        "SELECT id FROM film_tool_games WHERE client_game_id = ?", (client_id,)
    ).fetchone()
    args = (
        payload.get("analysisGameId"),
        payload.get("gameType", "my"),
        payload.get("date") or None,
        payload.get("ourTeam"),
        payload.get("opponent"),
        len(payload.get("rows") or []),
        state_json,
        client_id,
    )
    if existing:
        conn.execute(
            """UPDATE film_tool_games
                  SET analysis_key=?, game_type=?, game_date=?, our_team=?, opponent=?,
                      tag_count=?, state_json=?, updated_at=CURRENT_TIMESTAMP
                WHERE client_game_id=?""",
            args,
        )
    else:
        conn.execute(
            """INSERT INTO film_tool_games (
                client_game_id, analysis_key, game_type, game_date, our_team, opponent,
                tag_count, state_json
            ) VALUES (?,?,?,?,?,?,?,?)""",
            (
                client_id,
                payload.get("analysisGameId"),
                payload.get("gameType", "my"),
                payload.get("date") or None,
                payload.get("ourTeam"),
                payload.get("opponent"),
                len(payload.get("rows") or []),
                state_json,
            ),
        )


def merge_boxscore_model(hudl_caps_by_game: dict) -> dict:
    existing = load_boxscore_model() or {
        "source": "teach_from_boxscore",
        "boxscore_by_game": {},
        "game_count": 0,
    }
    by_game = dict(existing.get("boxscore_by_game") or {})
    by_game.update(hudl_caps_by_game)
    existing["boxscore_by_game"] = by_game
    existing["game_count"] = len(by_game)
    existing["hudl_merged_at"] = _utc_now()
    existing["principle"] = (
        "If AI event totals disagree with Hoopsalytics/MaxPreps/HUDL box scores, "
        "the AI is wrong. Cap detections to box-score counts."
    )
    DEFAULT_BOXSCORE_MODEL.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_BOXSCORE_MODEL.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    return existing


def import_all(source: Path, *, force_copy: bool = False, dry_run: bool = False,
               write_boxscore_model: bool = True) -> dict:
    disc = discover(source)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS.mkdir(parents=True, exist_ok=True)

    results = []
    hudl_caps = {}
    conn = None if dry_run else sqlite3.connect(str(DB_PATH))
    if conn:
        ensure_schema(conn)

    for pair in disc["paired"]:
        v = pair["video"]
        c = pair["csv"]
        game_id = pair["game_id"]
        film_id = pair["film_id"]
        box = parse_hudl_averages_csv(c["path"]) if c else None
        opponent = v["opponent"]
        location = v["location"]
        if location == "unknown" and c:
            location = c["location"]

        stored = f"hudl_{_slug(v['raw'])}.mp4"
        dest = UPLOADS / stored
        link_mode = None
        video_id = None
        if not dry_run:
            link_mode = link_or_copy(v["path"], dest, force_copy=force_copy)
            video_id = upsert_video(
                conn,
                stored=stored,
                original=v["path"].name,
                path=dest,
                opponent=opponent,
                game_id=game_id,
            )

        # referenceBoxScore: team totals as a pseudo single "team" player line
        # so reference_to_game_caps still works if needed; we also store team_totals.
        ref_box = None
        if box:
            ref_box = {
                "source": "hudl_averages",
                "source_file": box["source_file"],
                "team_token": "Liberty",
                "players": [],
                "team_totals": box["team_totals"],
                "by_period": box.get("by_period") or {},
            }
            hudl_caps[game_id] = {
                "team": box["team_totals"],
                "by_jersey": {},
                "by_period": box.get("by_period") or {},
                "source_file": box["source_file"],
                "team_token": "Liberty",
                "opponent": opponent,
                "location": location,
                "kind": v["kind"],
                "stored_filename": stored,
            }

        payload = {
            "id": film_id,
            "gameType": "my",
            "competitionType": v["kind"] if v["kind"] != "regular" else "non-conference",
            "date": "",
            "ourTeam": "Liberty",
            "opponent": opponent,
            "homeTeam": opponent if location == "away" else "Liberty",
            "awayTeam": "Liberty" if location == "away" else opponent,
            "gameResult": "",
            "outputDir": "",
            "lastTaggedTime": "—",
            "analysisGameId": game_id,
            "rows": [],
            "referenceBoxScore": ref_box,
            "source": "hudl",
            "importNotes": (
                "Imported from HUDL video + All Athletes averages CSV. "
                "Team totals only (no jersey lines, no Video Time). "
                "Use as box-score caps while AI runs on film."
            ),
            "videoStoredFilename": stored,
            "updatedAt": _utc_now(),
        }
        if not dry_run:
            upsert_film_tool(conn, payload)
            meta_path = OUT_DIR / f"{game_id}.json"
            meta_path.write_text(
                json.dumps(
                    {
                        "game_id": game_id,
                        "film_id": film_id,
                        "opponent": opponent,
                        "location": location,
                        "kind": v["kind"],
                        "video_id": video_id,
                        "stored_filename": stored,
                        "link_mode": link_mode,
                        "video_src": str(v["path"]),
                        "csv_src": str(c["path"]) if c else None,
                        "box": ref_box,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

        results.append(
            {
                "game_id": game_id,
                "film_id": film_id,
                "opponent": opponent,
                "location": location,
                "kind": v["kind"],
                "video": v["path"].name,
                "csv": c["path"].name if c else None,
                "video_id": video_id,
                "link_mode": link_mode,
                "points": (box or {}).get("team_totals", {}).get("points") if box else None,
                "pts_against": (box or {}).get("team_totals", {}).get("points_against") if box else None,
            }
        )

    if conn:
        conn.commit()
        conn.close()

    summary = {
        "source": str(source),
        "paired": len(results),
        "unmatched_videos": [
            {"file": v["path"].name, "opponent": v["opponent"], "location": v["location"]}
            for v in disc["unmatched_videos"]
        ],
        "unmatched_csvs": [
            {"file": c["path"].name, "opponent": c["opponent"], "location": c["location"]}
            for c in disc["unmatched_csvs"]
        ],
        "games": results,
        "imported_at": _utc_now(),
    }
    if not dry_run:
        (OUT_DIR / "import_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        if write_boxscore_model and hudl_caps:
            merge_boxscore_model(hudl_caps)
            summary["boxscore_model"] = str(DEFAULT_BOXSCORE_MODEL)
            summary["boxscore_hudl_games"] = len(hudl_caps)

    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--copy", action="store_true", help="Force full file copy instead of hardlink")
    ap.add_argument("--write-boxscore-model", action="store_true", default=True)
    ap.add_argument("--no-boxscore-model", action="store_true")
    args = ap.parse_args()

    summary = import_all(
        args.source,
        force_copy=args.copy,
        dry_run=args.dry_run,
        write_boxscore_model=not args.no_boxscore_model,
    )
    print("=" * 60)
    print("HUDL import")
    print("=" * 60)
    print(f"Source: {summary['source']}")
    print(f"Videos imported:  {summary['paired']}")
    print(f"With CSV caps:    {sum(1 for g in summary['games'] if g.get('csv'))}")
    print(f"Video no CSV:     {len(summary['unmatched_videos'])}")
    print(f"CSV no video:     {len(summary['unmatched_csvs'])}")
    for g in summary["games"]:
        flag = "CSV" if g.get("csv") else "vid"
        print(
            f"  [{flag}] {g['opponent']:22} {g['location']:7} {g['kind']:8} "
            f"PF={g['points']} PA={g['pts_against']}  {g['video']}"
        )
    if summary["unmatched_videos"]:
        print("\nUnmatched videos:")
        for v in summary["unmatched_videos"]:
            print(f"  {v['file']} ({v['opponent']}, {v['location']})")
    if summary["unmatched_csvs"]:
        print("\nUnmatched CSVs (stats only — no film pair):")
        for c in summary["unmatched_csvs"]:
            print(f"  {c['file']} ({c['opponent']}, {c['location']})")
    if args.dry_run:
        print("\nDry run — nothing written.")
    else:
        print(f"\nWrote {OUT_DIR / 'import_summary.json'}")
        if summary.get("boxscore_model"):
            print(f"Merged boxscore model ({summary.get('boxscore_hudl_games')} HUDL games)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
