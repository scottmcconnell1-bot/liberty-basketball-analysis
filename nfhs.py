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
import subprocess
import tempfile
from datetime import datetime

import requests
from bs4 import BeautifulSoup

NFHS_BASE_URL = "https://www.nfhsnetwork.com"
MEMBER_SERVICE_URL = "https://member.nfhsnetwork.com"
SEARCH_API_URL = "https://search-api.nfhsnetwork.com/v3"
LOGIN_URL = f"{MEMBER_SERVICE_URL}/oauth/token"


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


def download_nfhs_vod(game_id: str, email: str, password: str, output_dir: str) -> dict:
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
    output_path = os.path.join(output_dir, f"nfhs_{game_id}.mp4")

    # Get authenticated token
    token = get_nfhs_token(email, password)
    if not token:
        return {"success": False, "file_path": None, "file_size": 0, "error": "Could not authenticate with NFHS Network"}

    # Create a requests session with the token and export cookies for yt-dlp
    session = requests.Session()
    session.headers.update(_get_auth_headers(token))

    # NFHS uses token auth, not cookies. We need to pass the token to yt-dlp via headers.
    # Create a custom header file for yt-dlp
    header_file = os.path.join(tempfile.gettempdir(), f"nfhs_headers_{game_id}.txt")
    with open(header_file, 'w') as f:
        f.write(f"Authorization: Bearer {token}\n")
        f.write(f"User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36\n")

    nfhs_url = f"{NFHS_BASE_URL}/game/{game_id}"

    # Try yt-dlp with custom headers
    try:
        cmd = [
            "yt-dlp",
            "--no-check-certificates",
            "--add-header", f"Authorization: Bearer {token}",
            "--add-header", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "-o", output_path,
            "--merge-output-format", "mp4",
            "--retries", "3",
            "--fragment-retries", "3",
            nfhs_url
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
        if result.returncode == 0 and os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            _cleanup_files([header_file])
            return {"success": True, "file_path": output_path, "file_size": file_size, "error": None}
        else:
            error_msg = result.stderr[-500:] if result.stderr else "yt-dlp failed"
            _cleanup_files([header_file])
            return {"success": False, "file_path": None, "file_size": 0, "error": f"yt-dlp error: {error_msg}"}
    except FileNotFoundError:
        _cleanup_files([header_file])
        return {"success": False, "file_path": None, "file_size": 0, "error": "yt-dlp not installed. Install with: pip install yt-dlp"}
    except subprocess.TimeoutExpired:
        _cleanup_files([header_file])
        return {"success": False, "file_path": None, "file_size": 0, "error": "Download timed out (2 hour limit)"}


def _cleanup_files(paths: list):
    """Clean up temporary files."""
    for path in paths:
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
