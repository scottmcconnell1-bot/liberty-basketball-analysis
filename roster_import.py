"""Parse roster uploads from CSV, Excel, PDF, and MaxPreps printable PDF exports."""

from __future__ import annotations

import csv
import io
import re
from typing import BinaryIO

ROSTER_FILE_TYPES = ("auto", "csv", "excel", "pdf", "maxpreps_pdf")

_HEADER_WORDS = {
    "pos", "position", "#", "num", "number", "name", "grade", "class", "yr",
    "player", "height", "weight", "jersey",
}


def extract_pdf_text(pdf_file: BinaryIO) -> str:
    """Extract text from a PDF file object."""
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
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text


def is_maxpreps_printable_roster(text: str) -> bool:
    """Detect MaxPreps printable roster PDFs (browser print view export)."""
    return bool(re.search(
        r"maxpreps\.com/print/roster|Printable\s+.*Basketball\s+Roster|"
        r"#\s*Player\s+Grade\s+Position|Basketball\s+Roster\s*\(\d{4}-\d{2}\)",
        text,
        re.IGNORECASE,
    ))


def _normalize_player(
    *,
    jersey_number: str | None = None,
    name: str | None = None,
    grade: str | None = None,
    position: str | None = None,
) -> dict | None:
    name = (name or "").strip()
    if not name:
        return None
    jersey_number = (jersey_number or "").strip() or None
    grade = (grade or "").strip() or None
    position = (position or "").strip() or None

    label = ""
    if jersey_number and name:
        label = f"{jersey_number} - {name}"
    elif jersey_number:
        label = jersey_number
    else:
        label = name
    if grade:
        label += f", {grade}"

    return {
        "jersey_number": jersey_number,
        "name": name,
        "grade": grade,
        "position": position,
        "label": label,
    }


def _looks_like_header(parts: list[str]) -> bool:
    lower = [p.lower() for p in parts]
    return any(part in _HEADER_WORDS for part in lower)


def _cell_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _parse_roster_row_parts(parts: list[str]) -> dict | None:
    jersey_number = None
    name = None
    grade = None
    position = None

    if len(parts) >= 4 and parts[1].isdigit():
        position, jersey_number, name, grade = parts[0], parts[1], parts[2], parts[3]
    elif len(parts) >= 3 and parts[0].isdigit():
        jersey_number, name = parts[0], parts[1]
        if parts[2].isdigit() or parts[2].lower() in {"sr", "jr", "so", "fr"}:
            grade = parts[2]
            if len(parts) > 3:
                position = parts[3]
        else:
            position = parts[2]
    else:
        for part in parts:
            if part.isdigit() and jersey_number is None and len(part) <= 2:
                jersey_number = part
            elif part.lower() in {"sr", "jr", "so", "fr"} or (
                part.isdigit() and len(part) == 1 and grade is None
            ):
                grade = part
            elif part.upper() in {"PG", "SG", "SF", "PF", "C", "G", "F"} and position is None:
                position = part.upper()
            elif not name or len(part) > len(name):
                name = part

    return _normalize_player(
        jersey_number=jersey_number,
        name=name,
        grade=grade,
        position=position,
    )


def parse_roster_rows(rows: list[list]) -> list[dict]:
    """Parse roster rows from CSV or Excel into player dicts."""
    players: list[dict] = []
    for row in rows:
        parts = [_cell_str(cell) for cell in row if _cell_str(cell)]
        if not parts or _looks_like_header(parts):
            continue
        player = _parse_roster_row_parts(parts)
        if player:
            players.append(player)
    return players


def parse_roster_csv(text: str) -> list[dict]:
    """Parse CSV roster text into player dicts."""
    reader = csv.reader(io.StringIO(text))
    return parse_roster_rows(list(reader))


def parse_roster_excel(file: BinaryIO) -> list[dict]:
    """Parse an Excel workbook (.xlsx) into player dicts."""
    try:
        import openpyxl
    except ImportError as exc:
        raise ValueError(
            "Excel roster import requires openpyxl. Install with: pip install openpyxl"
        ) from exc

    file.seek(0)
    workbook = openpyxl.load_workbook(file, read_only=True, data_only=True)
    try:
        sheet = workbook.active
        rows = [list(row) for row in sheet.iter_rows(values_only=True)]
    finally:
        workbook.close()

    players = parse_roster_rows(rows)
    if not players:
        raise ValueError("No players found in Excel file. Check the sheet format.")
    return players


def _parse_csv_like_line(line: str) -> dict | None:
    if "," not in line:
        return None
    parts = [part.strip() for part in line.split(",") if part.strip()]
    if not parts or _looks_like_header(parts):
        return None
    rows = parse_roster_csv(line if "\n" in line else line + "\n")
    return rows[0] if rows else None


def parse_maxpreps_roster_text(text: str) -> list[dict]:
    """Parse MaxPreps printable roster PDF text into player dicts."""
    skip_patterns = [
        r"^\d{1,2}/\d{1,2}/\d{2,4},\s*\d{1,2}:\d{2}\s*(?:AM|PM)\b",
        r"^Printable\b",
        r"^America's Source",
        r"^Basketball Roster\s*\(",
        r"^Liberty Charter Basketball Roster",
        r"^Players\s*\(\d+\)",
        r"^Staff\s*\(\d+\)",
        r"^#\s*Player\s+Grade\s+Position",
        r"^maxpreps\.com",
        r"^https?://",
    ]
    player_line_re = re.compile(
        r"^(?:#\s*)?(\d{1,2})\s+"
        r"([A-Za-z][A-Za-z'\-\.\s]+?)\s+"
        r"(Sr|Jr|So|Fr|\d{1,2})\s*"
        r"([A-Z]{1,3}(?:\s*/\s*[A-Z]{1,3})?)?",
        re.IGNORECASE,
    )

    players: list[dict] = []
    in_staff = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.search(r"^Staff\s*\(\d+\)", line, re.IGNORECASE):
            in_staff = True
            continue
        if in_staff:
            continue
        if any(re.search(pattern, line, re.IGNORECASE) for pattern in skip_patterns):
            continue

        csv_player = _parse_csv_like_line(line)
        if csv_player:
            players.append(csv_player)
            continue

        match = player_line_re.match(line)
        if not match:
            continue
        jersey_number, name, grade, position = match.groups()
        player = _normalize_player(
            jersey_number=jersey_number,
            name=name.strip(),
            grade=grade,
            position=(position or "").upper() or None,
        )
        if player:
            players.append(player)
    return players


def parse_generic_roster_pdf_text(text: str) -> list[dict]:
    """Parse non-MaxPreps PDF roster text into player dicts."""
    players: list[dict] = []
    seen_labels: set[str] = set()

    def add_player(player: dict | None) -> None:
        if not player:
            return
        if player["label"] in seen_labels:
            return
        seen_labels.add(player["label"])
        players.append(player)

    if "," in text and re.search(r"POS|NAME|GRADE|#", text, re.IGNORECASE):
        for player in parse_roster_csv(text):
            add_player(player)
        if players:
            return players

    row_patterns = [
        re.compile(
            r"^(?:#\s*)?(\d{1,2})\s+([A-Za-z][A-Za-z'\-\.\s]+?)\s+"
            r"(\d{1,2}|Sr|Jr|So|Fr)\s+([A-Z]{1,3})?",
            re.IGNORECASE,
        ),
        re.compile(
            r"^([A-Z]{1,3})\s*,?\s*(\d{1,2})\s*,?\s*([A-Za-z][A-Za-z'\-\.\s]+)"
            r"(?:\s*,\s*(\d{1,2}|Sr|Jr|So|Fr))?",
            re.IGNORECASE,
        ),
    ]
    skip_patterns = [
        r"^Roster\b",
        r"^Team\b",
        r"^Coach\b",
        r"^Schedule\b",
        r"^Printable\b",
        r"^#\s*Player\b",
        r"^POS\b",
        r"^NAME\b",
    ]

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if any(re.search(pattern, line, re.IGNORECASE) for pattern in skip_patterns):
            continue

        csv_player = _parse_csv_like_line(line)
        if csv_player:
            add_player(csv_player)
            continue

        matched = False
        for pattern in row_patterns:
            match = pattern.match(line)
            if not match:
                continue
            groups = match.groups()
            if len(groups) == 4 and groups[0].isdigit():
                jersey_number, name, grade, position = groups
            else:
                position, jersey_number, name, grade = groups
            add_player(_normalize_player(
                jersey_number=jersey_number,
                name=name.strip(),
                grade=grade,
                position=(position or "").upper() or None,
            ))
            matched = True
            break
        if matched:
            continue

    return players


def detect_roster_file_type(filename: str, text: str | None = None) -> str:
    """Infer roster file type from filename and optional extracted text."""
    ext = (filename or "").rsplit(".", 1)[-1].lower() if filename else ""
    if ext == "csv":
        return "csv"
    if ext in {"xlsx", "xlsm"}:
        return "excel"
    if ext == "xls":
        return "excel"
    if ext != "pdf":
        return "csv" if "," in (text or "") else "pdf"

    content = text or ""
    if is_maxpreps_printable_roster(content):
        return "maxpreps_pdf"
    return "pdf"


def parse_roster_text(text: str, file_type: str = "auto", filename: str = "") -> tuple[list[dict], str]:
    """Parse roster text and return (players, detected_type)."""
    resolved_type = file_type
    if resolved_type == "auto":
        resolved_type = detect_roster_file_type(filename, text)

    if resolved_type == "csv":
        players = parse_roster_csv(text)
    elif resolved_type == "excel":
        raise ValueError("Excel files must be parsed with parse_roster_excel(), not parse_roster_text().")
    elif resolved_type == "maxpreps_pdf":
        players = parse_maxpreps_roster_text(text)
    elif resolved_type == "pdf":
        players = parse_generic_roster_pdf_text(text)
    else:
        raise ValueError(f"Unsupported file_type: {file_type}")

    if not players and resolved_type != "pdf":
        # Fall back to generic PDF parsing when a specialized parser finds nothing.
        players = parse_generic_roster_pdf_text(text)
        if players:
            resolved_type = "pdf"

    if not players:
        raise ValueError("No players found in file. Check the file type and format.")

    return players, resolved_type


def parse_roster_upload(file, file_type: str = "auto") -> dict:
    """Parse an uploaded roster file and return API-ready payload."""
    if file_type not in ROSTER_FILE_TYPES:
        raise ValueError(f"Invalid file_type. Use one of: {', '.join(ROSTER_FILE_TYPES)}")

    filename = getattr(file, "filename", "") or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if file_type in ("auto", "excel") and ext in {"xlsx", "xlsm", "xls"}:
        if ext == "xls":
            raise ValueError(
                "Legacy .xls files are not supported. Open in Excel and Save As .xlsx, or export CSV."
            )
        players = parse_roster_excel(file)
        detected_type = "excel"
    elif file_type in ("auto", "csv") and ext == "csv":
        text = file.read().decode("utf-8-sig", errors="replace")
        players, detected_type = parse_roster_text(text, file_type=file_type, filename=filename)
    elif file_type in ("auto", "pdf", "maxpreps_pdf") or ext == "pdf":
        text = extract_pdf_text(file)
        if not text.strip():
            raise ValueError("Could not extract text from PDF. Try a different file.")
        players, detected_type = parse_roster_text(text, file_type=file_type, filename=filename)
    elif file_type == "excel":
        players = parse_roster_excel(file)
        detected_type = "excel"
    else:
        text = file.read().decode("utf-8-sig", errors="replace")
        players, detected_type = parse_roster_text(text, file_type=file_type, filename=filename)

    return {
        "detected_type": detected_type,
        "players": players,
        "count": len(players),
    }
