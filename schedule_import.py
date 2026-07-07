"""Parse schedule uploads from MaxPreps printable PDF exports and other formats."""

from __future__ import annotations

import datetime
import re
from typing import BinaryIO


def is_maxpreps_printable_schedule(text: str) -> bool:
    """Detect MaxPreps printable schedule PDFs (browser print view export)."""
    return bool(re.search(
        r"maxpreps\.com/print/schedule|Printable\s+.*Basketball\s+Schedule|"
        r"Date\s+Opponent\s+Result|Basketball Schedule\s*\(\d{4}-\d{2}\)",
        text,
        re.IGNORECASE,
    ))


def _build_month_year_map(season_info: dict | None) -> dict[int, int]:
    month_year_map: dict[int, int] = {}
    if not season_info:
        return month_year_map
    start = season_info.get("start_date")
    end = season_info.get("end_date")
    if not start or not end:
        return month_year_map
    s_start = datetime.date.fromisoformat(start)
    s_end = datetime.date.fromisoformat(end)
    d = s_start
    while d <= s_end:
        month_year_map[d.month] = d.year
        if d.month == 12:
            d = datetime.date(d.year + 1, 1, 1)
        else:
            d = datetime.date(d.year, d.month + 1, 1)
    return month_year_map


def _normalize_compact_time(time_str: str) -> str:
    raw = (time_str or "").strip()
    compact = re.match(r"^(\d{1,2}):(\d{2})\s*([ap])m?$", raw, re.IGNORECASE)
    if compact:
        suffix = "AM" if compact.group(3).lower() == "a" else "PM"
        raw = f"{int(compact.group(1))}:{compact.group(2)} {suffix}"
    for fmt in ("%I:%M %p", "%I:%M%p", "%I:%M", "%H:%M"):
        try:
            return datetime.datetime.strptime(raw, fmt).strftime("%H:%M")
        except ValueError:
            continue
    return raw


def _parse_md_date(date_str: str, month_year_map: dict[int, int]) -> str | None:
    match = re.match(r"^(\d{1,2})/(\d{1,2})$", (date_str or "").strip())
    if not match:
        return None
    month, day = int(match.group(1)), int(match.group(2))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    year = month_year_map.get(month, datetime.datetime.now().year)
    try:
        return datetime.date(year, month, day).isoformat()
    except ValueError:
        return None


def _clean_opponent_name(raw: str) -> str:
    opponent = (raw or "").strip()
    opponent = re.sub(r"^\@\s+", "", opponent)
    opponent = re.sub(r"\s*\*+\s*$", "", opponent)
    opponent = re.sub(r"\s+", " ", opponent).strip()
    if not opponent:
        return ""
    # Prefer school name before parenthetical city when present.
    paren = re.match(r"^(.+?)\s*\([^)]+\)\s*$", opponent)
    if paren:
        return paren.group(1).strip()
    return opponent


def _is_skip_line(line: str) -> bool:
    if not line:
        return True
    skip_patterns = [
        r"^America's Source",
        r"^Mascot\b",
        r"^Coach\b",
        r"^Overall\b",
        r"^League\b",
        r"^Record Breakdown",
        r"^Home\s+\d",
        r"^Date\s+Opponent\s+Result",
        r"^Schedule Legend",
        r"^Conference Game",
        r"^Tournament Game",
        r"^Playoff Game",
        r"^https?://",
        r"maxpreps\.com",
        r"^Printable\b",
        r"^\d{1,2}/\d{1,2}/\d{2,4},\s+\d{1,2}:\d{2}\s*(?:AM|PM)",
        r"^--\s+\d+\s+of\s+\d+\s+--",
        r"^Liberty Charter Basketball Schedule",
    ]
    return any(re.search(pat, line, re.IGNORECASE) for pat in skip_patterns)


def _is_game_date_line(line: str) -> bool:
    return bool(re.match(r"^\d{1,2}/\d{1,2}$", line.strip()))


def _is_time_line(line: str) -> bool:
    return bool(re.match(r"^\d{1,2}:\d{2}\s*[ap]m?$", line.strip(), re.IGNORECASE))


def _is_result_line(line: str) -> bool:
    return bool(re.match(r"^\([WLT]\)\s+\d+", line.strip(), re.IGNORECASE))


RESULT_RE = re.compile(r"\(([WLT])\)\s*(\d+)\s*-\s*(\d+)", re.IGNORECASE)


def _parse_result_text(text: str) -> dict | None:
    match = RESULT_RE.search(text or "")
    if not match:
        return None
    letter = match.group(1).upper()
    score_a = int(match.group(2))
    score_b = int(match.group(3))
    # MaxPreps printable schedules list Liberty-Opp on wins and Opp-Liberty on losses.
    if letter == "W":
        liberty_score, opponent_score = score_a, score_b
    elif letter == "L":
        liberty_score, opponent_score = score_b, score_a
    else:
        liberty_score, opponent_score = score_a, score_b
    return {
        "result": {"W": "win", "L": "loss", "T": "tie"}[letter],
        "liberty_score": liberty_score,
        "opponent_score": opponent_score,
    }


def _is_conference_opponent(raw: str) -> bool:
    without_result = RESULT_RE.sub("", raw or "").strip()
    return bool(re.search(r"\*+", without_result))


def _split_opponent_and_result(text: str) -> tuple[str, dict | None, bool]:
    raw = (text or "").strip()
    is_conference = _is_conference_opponent(raw)
    result_info = _parse_result_text(raw)
    opponent_raw = RESULT_RE.sub("", raw).strip()
    opponent_raw = re.sub(r"\*+\s*$", "", opponent_raw).strip()
    if opponent_raw.startswith("@"):
        opponent_raw = opponent_raw[1:].strip()
    return _clean_opponent_name(opponent_raw), result_info, is_conference


def home_away_scores(location_type: str, liberty_score: int, opponent_score: int) -> tuple[int, int]:
    if location_type == "away":
        return opponent_score, liberty_score
    return liberty_score, opponent_score


def _parse_opponent_from_combined_rest(rest: str) -> str:
    opponent, _, _ = _split_opponent_and_result(rest)
    return opponent


def _consume_detail_lines(lines: list[str], start_index: int) -> tuple[int, str, str, list[str], dict | None]:
    """Return (next_index, game_time, tournament_name, notes_parts, result_info)."""
    game_time = ""
    tournament_name = ""
    notes_parts: list[str] = []
    result_info = None
    i = start_index

    while i < len(lines):
        next_line = lines[i].strip()
        if not next_line:
            i += 1
            continue
        if _is_game_date_line(next_line) or _is_combined_game_line(next_line):
            break
        if _is_skip_line(next_line):
            i += 1
            continue

        first_token = next_line.split()[0] if next_line.split() else ""
        if _is_time_line(first_token):
            game_time = _normalize_compact_time(first_token)
            tail = next_line[len(first_token):].strip()
            if tail.lower().startswith("game details:"):
                detail = tail.split(":", 1)[1].strip()
                if "tournament" in detail.lower() or "showcase" in detail.lower():
                    tournament_name = detail
                elif detail:
                    notes_parts.append(detail)
            i += 1
            continue

        if next_line.lower().startswith("location:"):
            i += 1
            continue
        if next_line.lower().startswith("game details:"):
            detail = next_line.split(":", 1)[1].strip()
            if detail:
                if "tournament" in detail.lower() or "showcase" in detail.lower():
                    tournament_name = detail
                else:
                    notes_parts.append(detail)
            i += 1
            continue
        if _is_result_line(next_line) or RESULT_RE.search(next_line):
            parsed = _parse_result_text(next_line)
            if parsed:
                result_info = parsed
            i += 1
            continue
        break

    return i, game_time, tournament_name, notes_parts, result_info


def _is_combined_game_line(line: str) -> bool:
    return bool(re.match(r"^\d{1,2}/\d{1,2}\s+\S", line.strip()))


def parse_maxpreps_schedule_text(
    text: str,
    *,
    pdf_team: str = "boys_hs",
    season_info: dict | None = None,
) -> list[dict]:
    """Parse MaxPreps printable schedule PDF text into game dicts."""
    month_year_map = _build_month_year_map(season_info)
    gender = "girls" if "girls" in pdf_team else "boys"
    level = "jr_high" if pdf_team.startswith("jr_") else "varsity"

    games: list[dict] = []
    lines = [line.strip() for line in text.splitlines()]

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if _is_skip_line(line):
            continue

        game_date = None
        opponent_name = ""
        location_type = "home"
        tournament_name = ""
        notes_parts: list[str] = []
        game_time = ""
        result_info = None
        is_conference = False

        combined = re.match(r"^(\d{1,2}/\d{1,2})\s+(.+)$", line)
        if combined and not _is_game_date_line(line):
            game_date = _parse_md_date(combined.group(1), month_year_map)
            if not game_date:
                continue
            if combined.group(2).strip().startswith("@"):
                location_type = "away"
            opponent_name, inline_result, is_conference = _split_opponent_and_result(combined.group(2))
            result_info = inline_result
            i, game_time, tournament_name, notes_parts, detail_result = _consume_detail_lines(lines, i)
            if detail_result:
                result_info = detail_result
        elif _is_game_date_line(line):
            game_date = _parse_md_date(line, month_year_map)
            if not game_date:
                continue

            if i < len(lines) and _is_time_line(lines[i]):
                game_time = _normalize_compact_time(lines[i])
                i += 1

            if i >= len(lines):
                continue

            opponent_line = lines[i].strip()
            i += 1
            if _is_skip_line(opponent_line) or _is_game_date_line(opponent_line) or _is_combined_game_line(opponent_line):
                continue

            if opponent_line.startswith("@"):
                location_type = "away"
            opponent_name, inline_result, is_conference = _split_opponent_and_result(opponent_line)
            result_info = inline_result

            i, extra_time, extra_tournament, extra_notes, detail_result = _consume_detail_lines(lines, i)
            if detail_result:
                result_info = detail_result
            if not game_time and extra_time:
                game_time = extra_time
            if extra_tournament:
                tournament_name = extra_tournament
            notes_parts.extend(extra_notes)
        else:
            continue

        if not opponent_name:
            continue

        game_record = {
            "game_date": game_date,
            "raw_date": line.split()[0] if combined else line,
            "game_time": game_time,
            "jv_game_time": "",
            "frosh_game_time": "",
            "opponent_name": opponent_name,
            "team": pdf_team,
            "level": level,
            "gender": gender,
            "location_type": location_type,
            "tournament_name": tournament_name,
            "notes": "; ".join(notes_parts),
            "is_conference": is_conference,
            "liberty_score": None,
            "opponent_score": None,
            "result": None,
            "status": "scheduled",
        }
        if result_info:
            game_record.update({
                "liberty_score": result_info["liberty_score"],
                "opponent_score": result_info["opponent_score"],
                "result": result_info["result"],
                "status": "completed",
            })
        games.append(game_record)

    return games


def extract_pdf_text(pdf_file: BinaryIO) -> str:
    try:
        import pdfplumber
    except ImportError:
        pdfplumber = None

    if pdfplumber is not None:
        text = ""
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        if text.strip():
            return text

    try:
        import PyPDF2
    except ImportError as exc:
        raise ValueError(
            "PDF parsing requires pdfplumber or PyPDF2. Install with: pip install pdfplumber"
        ) from exc

    pdf_file.seek(0)
    reader = PyPDF2.PdfReader(pdf_file)
    return "".join(page.extract_text() or "" for page in reader.pages)
