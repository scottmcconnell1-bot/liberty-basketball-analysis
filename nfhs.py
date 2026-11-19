"""
NFHS Network authentication and VOD download module.

Handles:
- Login to NFHS Network via member.nfhsnetwork.com/oauth/token
- Session management with token-based auth
- Game metadata lookup via search-api.nfhsnetwork.com
- VOD download using authenticated session
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

NFHS_BASE_URL = "https://www.nfhsnetwork.com"
MEMBER_SERVICE_URL = "https://member.nfhsnetwork.com"
SEARCH_API_URL = "https://search-api.nfhsnetwork.com/v3"
LOGIN_URL = f"{MEMBER_SERVICE_URL}/oauth/token"

_NFHS_GAME_ID_RE = re.compile(r"^(gam[a-zA-Z0-9]{8,}|g[a-zA-Z0-9]{5,19})$", re.IGNORECASE)
_NFHS_URL_PATTERNS = [
    re.compile(r"/events/[^/?#]+/(gam[a-zA-Z0-9]+)", re.IGNORECASE),
    re.compile(r"/game/(gam[a-zA-Z0-9]+)", re.IGNORECASE),
    re.compile(r"/embed/(gam[a-zA-Z0-9]+)", re.IGNORECASE),
    re.compile(r"/videos/(gam[a-zA-Z0-9]+)", re.IGNORECASE),
    re.compile(r"[?&]gameId=(gam[a-zA-Z0-9]+)", re.IGNORECASE),
    re.compile(r"[?&]game_id=(gam[a-zA-Z0-9]+)", re.IGNORECASE),
    re.compile(r"/(gam[a-zA-Z0-9]{8,})(?:[/?#]|$)", re.IGNORECASE),
]


def extract_nfhs_game_id(url_or_id: str | None) -> str | None:
    """Extract NFHS GameID from a URL or return a bare game ID."""
    if not url_or_id:
        return None

    text = url_or_id.strip()
    if not text:
        return None

    if not re.match(r"^https?://", text, re.IGNORECASE) and "nfhsnetwork.com" in text.lower():
        text = "https://" + text.lstrip("/")

    if _NFHS_GAME_ID_RE.match(text):
        return text

    for pattern in _NFHS_URL_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)

    return None


def parse_nfhs_input(url_or_id: str | None) -> dict:
    """Parse pasted NFHS input into game_id and optional watch URL."""
    text = (url_or_id or "").strip()
    game_id = extract_nfhs_game_id(text)
    if not game_id:
        return {"game_id": None, "watch_url": None}

    watch_url = None
    if re.match(r"^https?://", text, re.IGNORECASE):
        watch_url = text.split("?")[0].split("#")[0].rstrip("/")

    return {"game_id": game_id, "watch_url": watch_url}


def _get_token_path(email: str) -> str:
    """Get the path to the cached token file for a given email."""
    safe_email = re.sub(r'[^a-zA-Z0-9]', '_', email)
    return os.path.join(tempfile.gettempdir(), f"nfhs_token_{safe_email}.json")


def _save_token(email: str, token_data: dict):
    """Save OAuth token to disk."""
    path = _get_token_path(email)
    data = {
        "token": token_data,
        "saved_at": datetime.utcnow().isoformat()
    }
    with open(path, 'w') as f:
        json.dump(data, f)


def _load_token(email: str) -> dict | None:
    """Load cached OAuth token from disk if it exists and is not expired."""
    path = _get_token_path(email)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        token = data.get("token", {})
        # Check expiry
        created_at = token.get("created_at", 0)
        expires_in = token.get("expires_in", 0)
        if datetime.utcnow().timestamp() < created_at + expires_in:
            return token
    except (json.JSONDecodeError, KeyError, TypeError):
        pass
    return None


def _encrypt_password(password: str) -> str:
    """Simple XOR obfuscation for stored password."""
    import base64
    key = "liberty_basketball_nfhs_2026"
    encrypted = ''.join(chr(ord(c) ^ ord(key[i % len(key)])) for i, c in enumerate(password))
    return base64.b64encode(encrypted.encode()).decode()


def _decrypt_password(encrypted: str) -> str:
    """Decrypt XOR-obfuscated password."""
    import base64
    key = "liberty_basketball_nfhs_2026"
    decoded = base64.b64decode(encrypted.encode()).decode()
    return ''.join(chr(ord(c) ^ ord(key[i % len(key)])) for i, c in enumerate(decoded))


def _get_auth_headers(token: str) -> dict:
    """Get authorization headers for NFHS API calls."""
    return {
        "Authorization": f"Bearer {token}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }


def login_nfhs(email: str, password: str) -> dict:
    """
    Log in to NFHS Network.

    Returns: {
        "success": bool,
        "message": str,
        "session_valid": bool
    }
    """
    data = {
        "grant_type": "password",
        "username": email,
        "password": password,
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Origin": NFHS_BASE_URL,
        "Referer": f"{NFHS_BASE_URL}/",
    }

    try:
        resp = requests.post(LOGIN_URL, data=data, headers=headers, timeout=15)
    except requests.RequestException as e:
        return {"success": False, "message": f"Could not reach NFHS login: {e}", "session_valid": False}

    if resp.status_code != 200:
        return {"success": False, "message": f"Login failed (HTTP {resp.status_code}): {resp.text[:200]}", "session_valid": False}

    try:
        token_data = resp.json()
    except ValueError:
        return {"success": False, "message": "Invalid response from NFHS login", "session_valid": False}

    if "access_token" not in token_data:
        return {"success": False, "message": f"Login failed: {token_data}", "session_valid": False}

    # Save token
    _save_token(email, token_data)

    return {"success": True, "message": "Logged in successfully", "session_valid": True}


def get_nfhs_token(email: str, password: str) -> str | None:
    """
    Get a valid NFHS OAuth access token.
    Tries cached token first, then logs in if needed.
    Returns the access_token string or None.
    """
    # Try cached token first
    token = _load_token(email)
    if token:
        return token["access_token"]

    # Need to log in
    result = login_nfhs(email, password)
    if result["success"]:
        token = _load_token(email)
        if token:
            return token["access_token"]
    return None


def lookup_game(game_id: str, email: str, password: str) -> dict:
    """
    Look up game metadata from NFHS Network.

    Returns structured game data including teams, gender, level, date, VOD availability.
    """
    token = get_nfhs_token(email, password)
    if not token:
        return {"success": False, "error": "Could not authenticate with NFHS Network"}

    # Use search API to find the game
    try:
        resp = requests.get(
            f"{SEARCH_API_URL}/search?id={game_id}",
            headers=_get_auth_headers(token),
            timeout=15
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        return {"success": False, "error": f"Could not fetch game data: {e}"}

    try:
        data = resp.json()
    except ValueError:
        return {"success": False, "error": "Invalid response from NFHS search API"}

    items = data.get("items", [])
    if not items:
        return {"success": False, "error": f"No game found with ID: {game_id}"}

    game = items[0]

    # Extract team info
    teams = game.get("teams", [])
    home_team = None
    away_team = None
    for team in teams:
        if team.get("key") == game.get("home_team"):
            home_team = team.get("name") or team.get("short_name")
        else:
            away_team = team.get("name") or team.get("short_name")

    # If we couldn't distinguish home/away, just use order
    if not home_team and len(teams) >= 1:
        home_team = teams[0].get("name") or teams[0].get("short_name")
    if not away_team and len(teams) >= 2:
        away_team = teams[1].get("name") or teams[1].get("short_name")

    # Check VOD availability
    has_vod = game.get("has_vod", False)
    vods = game.get("vods", [])
    vod_key = vods[0].get("key") if vods else None

    # Get broadcast info
    broadcasts = game.get("broadcasts", [])
    broadcast_status = broadcasts[0].get("status") if broadcasts else None

    # Build headline from broadcast
    headline = None
    if broadcasts:
        headline = broadcasts[0].get("headline") or broadcasts[0].get("subheadline")

    return {
        "success": True,
        "game_id": game_id,
        "key": game.get("key"),
        "home_team": home_team,
        "away_team": away_team,
        "gender": game.get("gender", "").title() if game.get("gender") else None,
        "level": game.get("level", "").title() if game.get("level") else None,
        "sport": game.get("sport", "").title() if game.get("sport") else None,
        "game_type": game.get("game_type"),
        "date": game.get("start_time", "")[:10] if game.get("start_time") else None,
        "start_time": game.get("start_time"),
        "status": game.get("status"),
        "score": game.get("score"),
        "headline": headline,
        "vod_available": has_vod,
        "vod_key": vod_key,
        "broadcast_status": broadcast_status,
        "site_url": game.get("site_url"),
        "city": game.get("city"),
        "state": game.get("state_code"),
        "is_postseason": game.get("is_postseason", False),
        "raw_teams": [{"name": t.get("name"), "short_name": t.get("short_name"), "mascot": t.get("mascot"), "city": t.get("city"), "state": t.get("state_code")} for t in teams],
    }


def _yt_dlp_command() -> list[str]:
    """Resolve yt-dlp executable: PATH binary, else python -m yt_dlp from venv."""
    if shutil.which("yt-dlp"):
        return ["yt-dlp"]
    return [sys.executable, "-m", "yt_dlp"]


def _yt_dlp_available() -> bool:
    if shutil.which("yt-dlp"):
        return True
    try:
        result = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


_HLS_SEGMENT_RE = re.compile(r"hd(\d+)\.ts", re.IGNORECASE)


def _hls_segment_index(line: str) -> int | None:
    """Parse NFHS HLS segment number from ffmpeg log lines (e.g. hd116.ts)."""
    match = _HLS_SEGMENT_RE.search(line or "")
    return int(match.group(1)) if match else None


def _parse_yt_dlp_progress(line: str) -> dict | None:
    """Parse a yt-dlp progress line into percent/speed/eta."""
    if "[download]" not in line or "%" not in line:
        return None
    percent_match = re.search(r"\[download\]\s+(\d+(?:\.\d+)?)%", line)
    if not percent_match:
        return None
    percent = float(percent_match.group(1))
    speed_match = re.search(r"\bat\s+(\S+)", line)
    eta_match = re.search(r"\bETA\s+(\S+)", line)
    return {
        "percent": percent,
        "speed": speed_match.group(1) if speed_match else None,
        "eta": eta_match.group(1) if eta_match else None,
        "message": f"Downloading… {percent:.1f}%",
    }


def _friendly_download_phase(line: str) -> str | None:
    """Map yt-dlp startup lines to short user-facing status text (never raw logs)."""
    text = re.sub(r"\x1b\[[0-9;]*m", "", (line or "").strip())
    if not text or _parse_yt_dlp_progress(text):
        return None
    lowered = text.lower()
    if any(token in lowered for token in ("cloudfront", ".ts", "opening 'http", "[https @", "[ffmpeg")):
        return None
    if "extracting" in lowered or "[nfhs" in lowered:
        return "Connecting to NFHS…"
    if "downloading" in lowered and "playlist" in lowered:
        return "Finding video stream…"
    if "merging" in lowered:
        return "Merging video…"
    return None


def _emit_download_status(
    progress_callback,
    *,
    percent=None,
    speed=None,
    eta=None,
    message="",
    segments=None,
    last_segment=None,
) -> None:
    if not progress_callback:
        return
    payload = {"message": message}
    if percent is not None:
        payload["percent"] = percent
    if speed is not None:
        payload["speed"] = speed
    if eta is not None:
        payload["eta"] = eta
    if segments is not None:
        payload["segments"] = segments
    if last_segment is not None:
        payload["last_segment"] = last_segment
    progress_callback(**payload)


def _format_section_time(ms: int) -> str:
    total_sec = max(0, int(ms // 1000))
    hrs = total_sec // 3600
    mins = (total_sec % 3600) // 60
    secs = total_sec % 60
    if hrs:
        return f"{hrs}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


class NfhsDownloadControl:
    """Thread-safe handle for cancelling an in-progress yt-dlp download."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.cancelled = False
        self._proc = None
        self._output_path: str | None = None

    def attach(self, proc, output_path: str) -> None:
        with self._lock:
            self._proc = proc
            self._output_path = output_path

    def request_cancel(self) -> None:
        with self._lock:
            self.cancelled = True
            proc = self._proc
            output_path = self._output_path
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        if output_path:
            _cleanup_files([output_path])
            partial = f"{output_path}.part"
            if os.path.exists(partial):
                _cleanup_files([partial])


def download_nfhs_vod(
    game_id: str,
    email: str,
    password: str,
    output_dir: str,
    *,
    watch_url: str | None = None,
    progress_callback=None,
    start_ms: int | None = None,
    end_ms: int | None = None,
    download_control: NfhsDownloadControl | None = None,
) -> dict:
    """
    Download NFHS VOD using yt-dlp with authenticated session cookies.

    Returns: {
        "success": bool,
        "file_path": str,
        "file_size": int,
        "error": str
    }
    """
    os.makedirs(output_dir, exist_ok=True)
    is_section = start_ms is not None and end_ms is not None and end_ms > start_ms
    # A section download gets its own file: nfhs_<id>.mp4 may already hold the full
    # game in the library, and yt-dlp would replace it with the short clip.
    if is_section:
        output_path = os.path.join(output_dir, f"nfhs_{game_id}_clip_{int(start_ms)}_{int(end_ms)}.mp4")
    else:
        output_path = os.path.join(output_dir, f"nfhs_{game_id}.mp4")

    _emit_download_status(progress_callback, percent=0, message="Authenticating with NFHS…")
    token = get_nfhs_token(email, password)
    if not token:
        return {"success": False, "file_path": None, "file_size": 0, "error": "Could not authenticate with NFHS Network"}

    _emit_download_status(progress_callback, percent=0, message="Preparing download…")
    session = requests.Session()
    session.headers.update(_get_auth_headers(token))

    # NFHS uses token auth, not cookies. We need to pass the token to yt-dlp via headers.
    # Create a custom header file for yt-dlp
    header_file = os.path.join(tempfile.gettempdir(), f"nfhs_headers_{game_id}.txt")
    with open(header_file, 'w') as f:
        f.write(f"Authorization: Bearer {token}\n")
        f.write(f"User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36\n")

    nfhs_url = watch_url or f"{NFHS_BASE_URL}/game/{game_id}"

    if not _yt_dlp_available():
        _cleanup_files([header_file])
        return {
            "success": False,
            "file_path": None,
            "file_size": 0,
            "error": "yt-dlp not installed. From your project venv run: pip install yt-dlp",
        }

    # yt-dlp writes the video length it expects here (if the stream reports one), so a
    # recovered file can be checked against it. --print-to-file does not quiet the output.
    duration_file = os.path.join(tempfile.gettempdir(), f"nfhs_duration_{game_id}.txt")
    _cleanup_files([duration_file])
    temp_files = [header_file, duration_file]
    run_started = time.time()

    # Try yt-dlp with custom headers
    try:
        cmd = [
            *_yt_dlp_command(),
            "--print-to-file", "before_dl:%(duration)s", duration_file,
            "--no-check-certificates",
            "--newline",
            "--progress",
            "--socket-timeout", "30",
            "--concurrent-fragments", "4",
            "--add-header", f"Authorization: Bearer {token}",
            "--add-header", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "-o", output_path,
            "--merge-output-format", "mp4",
            "--retries", "3",
            "--fragment-retries", "3",
            nfhs_url,
        ]
        if is_section:
            section = f"*{_format_section_time(start_ms)}-{_format_section_time(end_ms)}"
            cmd = cmd[:-1] + ["--download-sections", section, cmd[-1]]
        _emit_download_status(progress_callback, percent=0, message="Connecting to NFHS…")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        if download_control:
            download_control.attach(proc, output_path)
        output_lines: list[str] = []
        segments_seen = 0
        last_segment = 0
        assert proc.stdout is not None
        for line in iter(proc.stdout.readline, ""):
            if download_control and download_control.cancelled:
                download_control.request_cancel()
                _cleanup_files(temp_files + list(_temp_paths(output_path)))
                return {
                    "success": False,
                    "file_path": None,
                    "file_size": 0,
                    "error": "Download cancelled",
                    "cancelled": True,
                }
            output_lines.append(line)
            if progress_callback:
                parsed = _parse_yt_dlp_progress(line)
                if parsed:
                    progress_callback(**parsed)
                else:
                    segment_index = _hls_segment_index(line)
                    if segment_index is not None:
                        segments_seen += 1
                        last_segment = max(last_segment, segment_index)
                        _emit_download_status(
                            progress_callback,
                            percent=0,
                            message=f"Downloading segments… ({segments_seen} received)",
                            segments=segments_seen,
                            last_segment=last_segment,
                        )
                    else:
                        phase_message = _friendly_download_phase(line)
                        if phase_message:
                            _emit_download_status(progress_callback, percent=0, message=phase_message)
        return_code = proc.wait(timeout=7200)
        if download_control and download_control.cancelled:
            _cleanup_files(temp_files + list(_temp_paths(output_path)))
            return {
                "success": False,
                "file_path": None,
                "file_size": 0,
                "error": "Download cancelled",
                "cancelled": True,
            }
        log_path = _write_download_log(game_id, output_lines, token, return_code)
        expected_s = _read_expected_duration(duration_file, start_ms if is_section else None,
                                             end_ms if is_section else None)
        _cleanup_files(temp_files)
        if return_code == 0 and os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            if progress_callback:
                progress_callback(percent=100.0, message="Download finished")
            return {"success": True, "file_path": output_path, "file_size": file_size, "error": None,
                    "log_path": log_path}

        # yt-dlp reported a failure. If the finished file is there, check it and
        # complete the last step ourselves instead of throwing away a full download.
        recovery_note = ""
        if os.path.exists(output_path) or os.path.exists(_temp_paths(output_path)[0]):
            _emit_download_status(progress_callback, percent=100, message="Checking the downloaded video…")
            try:
                ok, done = _recover_finished_download(
                    output_path, expected_s=expected_s, run_started=run_started
                )
            except OSError as exc:
                ok, done = False, f"could not finish the file: {exc}"
            # Leftover repair copies are never useful after this point.
            _cleanup_files(list(_temp_paths(output_path)))
            if not ok:
                recovery_note = f"\nThe Film Tool checked the file: {done}."
            if ok:
                if progress_callback:
                    progress_callback(percent=100.0, message="Download finished")
                return {
                    "success": True,
                    "file_path": output_path,
                    "file_size": os.path.getsize(output_path),
                    "error": None,
                    "warning": f"yt-dlp reported a problem at the end; the Film Tool {done}.",
                    "log_path": log_path,
                }

        combined = "".join(output_lines)
        error_msg = (combined or "yt-dlp failed")[-500:]
        if token:
            error_msg = error_msg.replace(token, "<token removed>")
        error_msg += recovery_note
        if log_path:
            error_msg += f"\n(Full log: {log_path})"
        return {"success": False, "file_path": None, "file_size": 0, "error": f"yt-dlp error: {error_msg}",
                "log_path": log_path}
    except FileNotFoundError:
        _cleanup_files(temp_files)
        return {
            "success": False,
            "file_path": None,
            "file_size": 0,
            "error": "yt-dlp not installed. From your project venv run: pip install yt-dlp",
        }
    except subprocess.TimeoutExpired:
        _cleanup_files(temp_files)
        return {"success": False, "file_path": None, "file_size": 0, "error": "Download timed out (2 hour limit)"}


_NFHS_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")


def _write_download_log(game_id: str, lines: list[str], token: str | None, return_code) -> str | None:
    """Keep the full yt-dlp output (token removed) so a failure can be diagnosed later."""
    try:
        os.makedirs(_NFHS_LOG_DIR, exist_ok=True)
        path = os.path.join(
            _NFHS_LOG_DIR, f"nfhs_download_{game_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )
        text = "".join(lines)
        if token:
            text = text.replace(token, "<token removed>")
        with open(path, "w", encoding="utf-8", errors="replace") as f:
            f.write(text)
            f.write(f"\n[film tool] yt-dlp exit code: {return_code}\n")
        return path
    except OSError:
        return None


def _probe_video(path: str) -> dict | None:
    """Return {format, has_video, duration} for a media file, or None if ffprobe cannot read it."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe or not os.path.exists(path) or os.path.getsize(path) == 0:
        return None
    try:
        res = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=format_name,duration:stream=codec_type",
             "-of", "json", path],
            capture_output=True, text=True, timeout=120,
        )
        if res.returncode != 0:
            return None
        info = json.loads(res.stdout or "{}")
        fmt = info.get("format", {})
        return {
            "format": fmt.get("format_name", ""),
            "has_video": any(s.get("codec_type") == "video" for s in info.get("streams", [])),
            "duration": float(fmt.get("duration") or 0),
        }
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def _plays_to_end(path: str) -> bool:
    """Decode the last few seconds: a cut-off or broken file fails here."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    try:
        res = subprocess.run(
            [ffmpeg, "-v", "error", "-sseof", "-5", "-i", path, "-f", "null", "-"],
            capture_output=True, text=True, timeout=300,
        )
        return res.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _is_good_mp4(path: str) -> bool:
    info = _probe_video(path)
    return bool(
        info and info["has_video"] and info["duration"] > 0
        and ("mp4" in info["format"] or "mov" in info["format"])
        and _plays_to_end(path)
    )


def _replace_with_retry(src: str, dst: str, attempts: int = 10, delay: float = 2.0) -> None:
    """os.replace, retrying while Windows has the file open (virus scan, video preview)."""
    for n in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if n == attempts - 1:
                raise
            time.sleep(delay)


def _remux_to_mp4(src: str, dst: str) -> bool:
    """Copy the streams into a normal MP4 (what yt-dlp's final 'fixup' step does)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    try:
        res = subprocess.run(
            [ffmpeg, "-y", "-v", "error", "-i", src, "-map", "0", "-c", "copy",
             "-bsf:a", "aac_adtstoasc", "-movflags", "+faststart", "-f", "mp4", dst],
            capture_output=True, text=True, timeout=3600,
        )
        return res.returncode == 0 and _is_good_mp4(dst)
    except (OSError, subprocess.TimeoutExpired):
        return False


def _temp_paths(output_path: str) -> tuple[str, str]:
    """(yt-dlp's fixup output, the Film Tool's own remux output) for a final file name."""
    base, _ext = os.path.splitext(output_path)
    return base + ".temp.mp4", base + ".filmtool_fix.mp4"


def _long_enough(path: str, expected_s: float | None) -> bool:
    """Soft length gate: only applies when the expected length is known."""
    if not expected_s or expected_s <= 0:
        return True
    info = _probe_video(path)
    if not info:
        return False
    return info["duration"] >= 0.95 * expected_s or expected_s - info["duration"] <= 30


def _written_this_run(path: str, run_started: float | None) -> bool:
    """Never treat a file left over from an earlier download as this run's result."""
    if run_started is None:
        return True
    try:
        return os.path.getmtime(path) >= run_started - 2
    except OSError:
        return False


def _recover_finished_download(
    output_path: str, *, expected_s: float | None = None, run_started: float | None = None
) -> tuple[bool, str]:
    """
    yt-dlp only writes the final file name after every piece has downloaded, so if that
    file exists the download itself finished; a non-zero exit then means a last step
    (usually the MP4 'fixup') failed. Check the file and finish that step ourselves.
    Returns (ok, what_was_done). Never accepts a file from an earlier run or one much
    shorter than the expected length (when known).
    """
    leftover, fixed = _temp_paths(output_path)
    if (os.path.exists(leftover) and _written_this_run(leftover, run_started)
            and _is_good_mp4(leftover) and _long_enough(leftover, expected_s)):
        _replace_with_retry(leftover, output_path)
        return True, "finished yt-dlp's interrupted MP4 repair"
    if not os.path.exists(output_path):
        return False, "no finished file"
    if not _written_this_run(output_path, run_started):
        return False, "the video file is from an earlier download, not this one"
    if not _long_enough(output_path, expected_s):
        return False, "the video is much shorter than NFHS says it should be"
    if _is_good_mp4(output_path):
        _cleanup_files([leftover])
        return True, "file checked: complete, plays to the end"
    info = _probe_video(output_path)
    if info and info["has_video"] and info["duration"] > 0:
        need = int(os.path.getsize(output_path) * 1.1)
        if shutil.disk_usage(os.path.dirname(os.path.abspath(output_path))).free < need:
            return False, f"not enough free disk space to repair it (needs about {need // 2**30 + 1} GB)"
        if _remux_to_mp4(output_path, fixed) and _long_enough(fixed, expected_s):
            _replace_with_retry(fixed, output_path)
            _cleanup_files([leftover])
            return True, "repaired the stream into a normal MP4"
    return False, "file is not a playable video"


def _read_expected_duration(path: str, start_ms: int | None, end_ms: int | None) -> float | None:
    """Section length for clips; otherwise the duration yt-dlp reported (if any)."""
    if start_ms is not None and end_ms is not None and end_ms > start_ms:
        return (end_ms - start_ms) / 1000.0
    try:
        with open(path, encoding="utf-8") as f:
            vals = [v.strip() for v in f.read().split() if v.strip()]
        for v in reversed(vals):
            try:
                d = float(v)
                if d > 0:
                    return d
            except ValueError:
                continue
    except OSError:
        pass
    return None


def _cleanup_files(paths: list):
    """Clean up temporary files."""
    for path in paths:
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass


def register_nfhs_download(
    db,
    file_path: str,
    nfhs_game_id: str,
    *,
    opponent_name: str | None = None,
    home_team: str | None = None,
    away_team: str | None = None,
    nfhs_url: str | None = None,
) -> dict:
    """Register a downloaded NFHS VOD in the videos library for future review."""
    if not os.path.exists(file_path):
        raise ValueError(f"Downloaded file not found: {file_path}")

    stored_filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    opponent = (opponent_name or away_team or home_team or nfhs_game_id).strip()
    original_filename = (
        stored_filename if stored_filename.startswith(f"nfhs_{nfhs_game_id}_clip_")
        else f"nfhs_{nfhs_game_id}.mp4"
    )
    nfhs_url = nfhs_url or f"{NFHS_BASE_URL}/game/{nfhs_game_id}"

    existing = db.execute(
        "SELECT id, stored_filename, game_id, file_size_bytes FROM videos WHERE stored_filename=?",
        (stored_filename,),
    ).fetchone()
    if existing:
        # Same file downloaded again (it was rewritten on disk): keep the row current.
        if existing["file_size_bytes"] != file_size:
            db.execute(
                "UPDATE videos SET file_size_bytes=?, file_path=? WHERE id=?",
                (file_size, file_path, existing["id"]),
            )
        return {
            "video_id": existing["id"],
            "stored_filename": existing["stored_filename"],
            "game_id": existing["game_id"],
            "already_saved": True,
        }

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    analysis_game_id = f"nfhs_{nfhs_game_id}_{ts}"

    game_row = db.execute(
        "SELECT id FROM games WHERE nfhs_game_id=? ORDER BY id DESC LIMIT 1",
        (nfhs_game_id,),
    ).fetchone()
    if game_row:
        relational_game_id = game_row["id"]
    else:
        cur = db.execute(
            """INSERT INTO games (source_type, source_key, nfhs_game_id, nfhs_url)
               VALUES (?, ?, ?, ?)""",
            ("nfhs_vod", file_path, nfhs_game_id, nfhs_url),
        )
        relational_game_id = cur.lastrowid

    video_cur = db.execute(
        """INSERT INTO videos (original_filename, stored_filename, file_path, file_size_bytes,
                               opponent, game_id, relational_game_id, is_duplicate, duplicate_of_id)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            original_filename,
            stored_filename,
            file_path,
            file_size,
            opponent,
            analysis_game_id,
            relational_game_id,
            0,
            None,
        ),
    )

    existing_source = db.execute(
        "SELECT id FROM sources WHERE game_id=? AND source_type='nfhs_vod' AND source_path=?",
        (relational_game_id, file_path),
    ).fetchone()
    if not existing_source:
        db.execute(
            "INSERT INTO sources (game_id, source_type, source_path) VALUES (?,?,?)",
            (relational_game_id, "nfhs_vod", file_path),
        )

    return {
        "video_id": video_cur.lastrowid,
        "stored_filename": stored_filename,
        "game_id": analysis_game_id,
        "relational_game_id": relational_game_id,
        "already_saved": False,
    }
