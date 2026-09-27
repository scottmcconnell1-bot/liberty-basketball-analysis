#!/usr/bin/env python3
"""Score Q1 precision events against Film Tool tags. Does not persist or copy tags."""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from event_generator import (  # noqa: E402
    _interpolate_ball,
    _cluster_players_spatially,
    build_ball_track,
    build_possession_segments,
    find_ball_possession,
    generate_precision_events_from_segments,
)
from film_tool_tags import load_manual_tags  # noqa: E402
from manual_tag_teach import time_to_ms  # noqa: E402

GAME = "jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334"
WINDOW_MS = 960700
Q2_END_MS = 32 * 60 * 1000 + 14 * 1000  # Scott: Q2 ends 32:14
TOL_MS = 8000
DB = ROOT / "film_analysis.db"


def _shot_kind(event: dict) -> str | None:
    et = str(event.get("event_type") or "").lower()
    if et == "shot":
        try:
            details = json.loads(event.get("details_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            details = {}
        kind = str(details.get("shot_kind") or details.get("shot_type") or "").lower()
        if kind in {"ft", "free_throw"}:
            return "FT"
        if kind in {"3", "3pt", "three"}:
            return "3PT"
        if kind in {"2", "2pt"}:
            return "2PT"
        return "2PT"
    if "free" in et:
        return "FT"
    if "three" in et:
        return "3PT"
    if et in {"made_two", "missed_two"}:
        return "2PT"
    return None


def main() -> int:
    payload = load_manual_tags(GAME) or {}
    manual = []
    q2_manual = []
    q2_to = 0
    for row in payload.get("rows") or []:
        et = str(row.get("eventtype") or "")
        ts = time_to_ms(row.get("start"))
        if et == "Turnover" and WINDOW_MS < ts <= Q2_END_MS:
            q2_to += 1
        if et not in {"2PT", "3PT", "FT"}:
            continue
        item = {"ts": ts, "kind": et, "result": str(row.get("result") or "")}
        if ts <= WINDOW_MS:
            manual.append(item)
        elif ts <= Q2_END_MS:
            q2_manual.append(item)

    conn = sqlite3.connect(str(DB))
    q1_n = conn.execute(
        "SELECT COUNT(*) FROM detections WHERE game_id = ? AND timestamp_ms <= ?",
        (GAME, Q2_END_MS),
    ).fetchone()[0]
    ball_by_kind = {}
    for kind in ("FT", "2PT", "3PT"):
        hits = 0
        for row in [m for m in manual if m["kind"] == kind]:
            n = conn.execute(
                """
                SELECT COUNT(*) FROM detections
                WHERE game_id = ? AND object_class IN ('ball', 'sports ball', 'sports_ball')
                  AND timestamp_ms BETWEEN ? AND ?
                """,
                (GAME, row["ts"] - 1500, row["ts"] + 1500),
            ).fetchone()[0]
            if n:
                hits += 1
        ball_by_kind[kind] = {"tags": sum(1 for m in manual if m["kind"] == kind), "with_ball": hits}

    print(json.dumps({"q1_detections": q1_n, "ball_near_tags": ball_by_kind}, indent=2), flush=True)

    df = pd.read_sql_query(
        """
        SELECT * FROM detections
        WHERE game_id = ? AND timestamp_ms <= ?
        """,
        conn,
        params=(GAME, Q2_END_MS),
    )
    conn.close()
    if "object_class" in df.columns:
        df["class_name"] = df["object_class"].replace(
            {"sports ball": "ball", "sports_ball": "ball"}
        ).fillna(df["object_class"])
    if "tracker_id" not in df.columns:
        df["tracker_id"] = pd.NA

    df = _interpolate_ball(df)
    df = _cluster_players_spatially(df, n_clusters=10, conn=None, game_id=GAME)
    possessed = find_ball_possession(df)
    segments = build_possession_segments(possessed)
    ball_track = build_ball_track(df)
    events = generate_precision_events_from_segments(
        GAME, segments, ball_track, detections_df=df
    )
    q1_events = [e for e in events if int(e.get("timestamp_ms") or 0) <= WINDOW_MS]
    q2_events = [
        e for e in events
        if WINDOW_MS < int(e.get("timestamp_ms") or 0) <= Q2_END_MS
    ]

    def shot_rows(items):
        rows = []
        for event in items:
            kind = _shot_kind(event)
            if kind is None or str(event.get("event_type") or "").lower() != "shot":
                continue
            try:
                details = json.loads(event.get("details_json") or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                details = {}
            rows.append(
                {
                    "ts": int(event.get("timestamp_ms") or 0),
                    "kind": kind,
                    "ft_formation": details.get("ft_formation"),
                    "result": str(event.get("shot_result") or ""),
                }
            )
        return rows

    shots = shot_rows(q1_events)
    q2_shots = shot_rows(q2_events)

    used = set()
    matched = []
    for tag in manual:
        best_i = None
        best_dt = None
        for i, shot in enumerate(shots):
            if i in used:
                continue
            dt = abs(shot["ts"] - tag["ts"])
            if dt > TOL_MS:
                continue
            if best_dt is None or dt < best_dt:
                best_dt = dt
                best_i = i
        if best_i is None:
            matched.append({"tag": tag, "ai": None, "dt": None})
            continue
        used.add(best_i)
        matched.append({"tag": tag, "ai": shots[best_i], "dt": best_dt})

    kind_agree = sum(
        1 for row in matched if row["ai"] and row["ai"]["kind"] == row["tag"]["kind"]
    )
    ft_tags = [row for row in matched if row["tag"]["kind"] == "FT"]
    ft_called = sum(1 for row in ft_tags if row["ai"] and row["ai"]["kind"] == "FT")
    extra = [s for i, s in enumerate(shots) if i not in used]
    by_ai = Counter(s["kind"] for s in shots)
    by_form = Counter(str(s.get("ft_formation")) for s in shots)

    q2_used = set()
    q2_matched = 0
    for tag in q2_manual:
        best_i = None
        best_dt = None
        for i, shot in enumerate(q2_shots):
            if i in q2_used:
                continue
            dt = abs(shot["ts"] - tag["ts"])
            if dt > TOL_MS:
                continue
            if best_dt is None or dt < best_dt:
                best_dt = dt
                best_i = i
        if best_i is None:
            continue
        q2_used.add(best_i)
        q2_matched += 1
    q2_extra = [s for i, s in enumerate(q2_shots) if i not in q2_used]
    q2_ai_makes = sum(1 for s in q2_shots if str(s.get("result") or "").lower() == "make")
    q2_you_makes = sum(1 for t in q2_manual if str(t["result"]).lower() in {"make", "made"})
    q2_ai_to = sum(1 for e in q2_events if str(e.get("event_type") or "").lower() == "turnover")

    print(
        json.dumps(
            {
                "manual_shots": len(manual),
                "ai_shots": len(shots),
                "ai_by_kind": dict(by_ai),
                "ft_formation_values": dict(by_form),
                "matched": sum(1 for row in matched if row["ai"]),
                "kind_agree": kind_agree,
                "ft_tags": len(ft_tags),
                "ft_called_ft": ft_called,
                "manual_only": sum(1 for row in matched if row["ai"] is None),
                "ai_only": len(extra),
                "events_total": len(q1_events),
                "q2": {
                    "manual_shots": len(q2_manual),
                    "ai_shots": len(q2_shots),
                    "ai_by_kind": dict(Counter(s["kind"] for s in q2_shots)),
                    "matched": q2_matched,
                    "ai_only": len(q2_extra),
                    "manual_only": len(q2_manual) - q2_matched,
                    "you_makes": q2_you_makes,
                    "ai_makes": q2_ai_makes,
                    "you_to": q2_to,
                    "ai_to": q2_ai_to,
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
