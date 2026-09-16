"""Fetch MaxPreps rankings and schedule results over HTTP (no Linux Chromium)."""

from __future__ import annotations

import os
import re
from datetime import date
from html.parser import HTMLParser

STATE_SLUG_OVERRIDES = {"idaho": "id"}

DIVISION_IDS = {
    ("id", "boys"): "b006084a-35a3-4277-b62e-8782f19ac85a",
    ("id", "girls"): "17ff4bb2-1a40-4f38-a3e1-637f78af15f2",
}

TEAM_NAME = "Liberty Charter"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

RESULT_RE = re.compile(r"\b([WL])\s+(\d+)\s*[-–]\s*(\d+)\b")
RANK_LINE_RE = re.compile(
    r"(?im)^\s*\|?\s*(\d{1,2})\s*\|?\s+Liberty Charter\b"
)
DATE_LINE_RE = re.compile(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?")
ARIA_RESULT_RE = re.compile(
    r'aria-label="([WL])\s+(\d+)\s*[-–]\s*(\d+)\s+(vs|at)\s+([^"]+?),\s*(\d{1,2})/(\d{1,2})"',
    re.I,
)
CONF_ON_DATE_RE = re.compile(
    r"On (\d{1,2})/(\d{1,2}),.*? (non-conference|conference tournament|conference) ",
    re.I,
)


def basketball_season_slug(today: date | None = None) -> str:
    """School-year slug MaxPreps uses, e.g. 2025-26 → '25-26'.

    High-school basketball is Nov–Mar. Before November, the completed
    previous season is still the one with rankings and scores.
    """
    today = today or date.today()
    start_year = today.year if today.month >= 11 else today.year - 1
    return f"{start_year % 100:02d}-{(start_year + 1) % 100:02d}"


def ranking_url(state: str, gender: str, season_slug: str | None = None) -> str:
    state_slug = STATE_SLUG_OVERRIDES.get(state.lower().replace(" ", "-"), state.lower().replace(" ", "-"))
    gender_slug = "boys" if gender == "boys" else "girls"
    season_slug = season_slug or basketball_season_slug()
    div_id = DIVISION_IDS.get((state_slug, gender_slug))
    if gender_slug == "girls":
        url = f"https://www.maxpreps.com/{state_slug}/basketball/girls/{season_slug}/class/class-2a/rankings/1/"
    else:
        url = f"https://www.maxpreps.com/{state_slug}/basketball/{season_slug}/class/class-2a/rankings/1/"
    if div_id:
        url += f"?statedivisionid={div_id}"
    return url


def schedule_url(gender: str = "boys", season_slug: str | None = None) -> str:
    season_slug = season_slug or basketball_season_slug()
    if gender == "girls":
        return (
            "https://www.maxpreps.com/id/nampa/liberty-charter-patriots/"
            f"basketball/girls/{season_slug}/schedule/"
        )
    return (
        "https://www.maxpreps.com/id/nampa/liberty-charter-patriots/"
        f"basketball/{season_slug}/schedule/"
    )


def fetch_url(url: str, timeout: int = 30) -> str:
    import requests

    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.text


def parse_liberty_ranking(text: str) -> int | None:
    """Return Liberty Charter's rank from a MaxPreps rankings page or table dump."""
    if not text:
        return None
    match = RANK_LINE_RE.search(text)
    if match:
        rank = int(match.group(1))
        if 1 <= rank <= 50:
            return rank

    class _RankTable(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_row = False
            self.cells: list[str] = []
            self.cur = ""
            self.rank = None

        def handle_starttag(self, tag, attrs):
            if tag == "tr":
                self.in_row = True
                self.cells = []
                self.cur = ""
            elif tag in ("td", "th") and self.in_row:
                self.cur = ""

        def handle_endtag(self, tag):
            if tag in ("td", "th") and self.in_row:
                self.cells.append(self.cur.strip())
                self.cur = ""
            elif tag == "tr" and self.in_row:
                self.in_row = False
                row = " ".join(self.cells)
                if TEAM_NAME.lower() in row.lower() and self.cells:
                    for cell in self.cells:
                        if cell.isdigit():
                            n = int(cell)
                            if 1 <= n <= 50:
                                self.rank = n
                                return

        def handle_data(self, data):
            if self.in_row:
                self.cur += data

    parser = _RankTable()
    try:
        parser.feed(text)
    except Exception:
        return None
    return parser.rank


def _season_iso_date(month: int, day: int, season_start_year: int) -> str:
    year = season_start_year if month >= 11 else season_start_year + 1
    return f"{year:04d}-{month:02d}-{day:02d}"


def _scores_from_result(wl: str, first: int, second: int) -> tuple[int, int]:
    """MaxPreps prints W/L then winner-loser, so L 70-51 means Liberty scored 51."""
    if wl == "W":
        return first, second
    return second, first


def _parse_opponent_cell(cell: str) -> tuple[str | None, str, bool]:
    conference = "*" in cell
    cleaned = cell.replace("*", " ")
    loc = "home"
    opp = None
    vs_m = re.search(r"\bvs\.?\s+(.+)", cleaned, re.I)
    at_m = re.search(r"^\s*@\s+(.+)", cleaned)
    if vs_m:
        opp = vs_m.group(1).strip()
        loc = "home"
    elif at_m:
        opp = at_m.group(1).strip()
        loc = "away"
    if opp:
        opp = re.sub(r"\s{2,}", " ", opp).strip(" |")
    return opp, loc, conference


def _conference_by_date(text: str, season_start_year: int) -> dict[str, bool]:
    flags = {}
    for match in CONF_ON_DATE_RE.finditer(text):
        month, day, kind = int(match.group(1)), int(match.group(2)), match.group(3).lower()
        flags[_season_iso_date(month, day, season_start_year)] = kind == "conference"
    return flags


def parse_schedule_results(text: str, season_start_year: int = 2025) -> list[dict]:
    """Parse MaxPreps schedule rows into score dicts."""
    games = []
    if not text:
        return games
    conf_by_date = _conference_by_date(text, season_start_year)
    seen = set()

    for match in ARIA_RESULT_RE.finditer(text):
        wl, first, second, loc_word, opp, month, day = match.groups()
        first, second, month, day = int(first), int(second), int(month), int(day)
        liberty_score, opponent_score = _scores_from_result(wl.upper(), first, second)
        game_date = _season_iso_date(month, day, season_start_year)
        if game_date in seen:
            continue
        seen.add(game_date)
        games.append({
            "game_date": game_date,
            "opponent_name": opp.strip(),
            "location_type": "away" if loc_word.lower() == "at" else "home",
            "result": "win" if wl.upper() == "W" else "loss",
            "liberty_score": liberty_score,
            "opponent_score": opponent_score,
            "is_conference": bool(conf_by_date.get(game_date)),
        })

    if games:
        return games

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("| ---") or "Date/Time" in line:
            continue
        result_m = RESULT_RE.search(line)
        date_m = DATE_LINE_RE.search(line)
        if not result_m or not date_m:
            continue
        wl, first, second = result_m.group(1), int(result_m.group(2)), int(result_m.group(3))
        month, day = int(date_m.group(1)), int(date_m.group(2))
        liberty_score, opponent_score = _scores_from_result(wl, first, second)
        game_date = _season_iso_date(month, day, season_start_year)

        opp = None
        loc = "home"
        conference = False
        if "|" in line:
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 2:
                opp, loc, conference = _parse_opponent_cell(cells[1])
        if opp is None:
            opp, loc, conference = _parse_opponent_cell(line)
        if game_date in conf_by_date:
            conference = conf_by_date[game_date]

        games.append({
            "game_date": game_date,
            "opponent_name": opp,
            "location_type": loc,
            "result": "win" if wl == "W" else "loss",
            "liberty_score": liberty_score,
            "opponent_score": opponent_score,
            "is_conference": conference,
        })
    return games


def apply_results_to_season(db, season_id: int, parsed: list[dict], save_fn) -> tuple[int, list[str]]:
    """Write parsed MaxPreps scores onto scheduled_games matched by date."""
    matched = 0
    unmatched = []
    for game in parsed:
        row = db.execute(
            "SELECT id FROM scheduled_games WHERE season_id = ? AND game_date = ?",
            (season_id, game["game_date"]),
        ).fetchone()
        if not row:
            unmatched.append(f"{game['game_date']} {game.get('opponent_name')}")
            continue
        save_fn(
            db,
            row["id"],
            game["liberty_score"],
            game["opponent_score"],
            is_conference=bool(game.get("is_conference")),
        )
        matched += 1
    return matched, unmatched


def scrape_ranking(state: str, gender: str, season_slug: str | None = None) -> dict:
    """Return {ranking, url, error} using HTTP first, Playwright only as fallback."""
    url = ranking_url(state, gender, season_slug)
    error = None
    ranking = None
    try:
        html = fetch_url(url)
        ranking = parse_liberty_ranking(html)
        if ranking is None:
            error = "Liberty Charter not found in MaxPreps rankings table."
    except Exception as exc:
        error = str(exc)
        ranking = _playwright_ranking_fallback(url)

    return {"ranking": ranking, "url": url, "error": error if ranking is None else None}


def playwright_chromium_kwargs() -> dict:
    """Launch Chromium without a Linux snap path so Windows/macOS work."""
    kwargs = {"headless": True, "args": ["--no-sandbox", "--disable-setuid-sandbox"]}
    path = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")
    if path and os.path.exists(path):
        kwargs["executable_path"] = path
    return kwargs


def _playwright_ranking_fallback(url: str) -> int | None:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(**playwright_chromium_kwargs())
            page = browser.new_page()
            page.set_default_timeout(30000)
            page.goto(url, wait_until="domcontentloaded")
            html = page.content()
            browser.close()
        return parse_liberty_ranking(html)
    except Exception:
        return None
