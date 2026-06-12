#!/usr/bin/env python3
"""Download and analyze Caldwell vs game from NFHS Network."""
import sys, os, json, subprocess, sqlite3, glob

sys.path.insert(0, '/home/monk-admin/PROJECTS/liberty-basketball-analysis')
from nfhs import get_nfhs_token, _decrypt_password, _encrypt_password, lookup_game, download_nfhs_vod

# === CONFIGURATION ===
EMAIL = "smcconnell@legacycharterschool.net"
PASSWORD = "Kourtney@1"
GAME_ID = "gamfad8d650d0"
GAME_URL = f"https://www.nfhsnetwork.com/events/caldwell-high-school-caldwell-id/{GAME_ID}"
OUTPUT_DIR = "/home/monk-admin/PROJECTS/liberty-basketball-analysis/videos"
DB_PATH = "/home/monk-admin/PROJECTS/liberty-basketball-analysis/film_analysis.db"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# === STEP 1: Store credentials ===
print("=== STEP 1: Storing credentials ===")
password_enc = _encrypt_password(PASSWORD)
conn = sqlite3.connect(DB_PATH)
conn.execute("UPDATE nfhs_credentials SET is_active=0 WHERE is_active=1")
conn.execute(
    "INSERT INTO nfhs_credentials (email, password_enc, is_active) VALUES (?, ?, 1)",
    (EMAIL, password_enc)
)
conn.commit()
print(f"  Stored: {EMAIL}")
conn.close()

# === STEP 2: Authenticate ===
print("\n=== STEP 2: Authenticating ===")
token = get_nfhs_token(EMAIL, PASSWORD)
if not token:
    print("  ERROR: Authentication failed")
    sys.exit(1)
print(f"  Token OK: {token[:15]}...")

# === STEP 3: Look up game metadata ===
print("\n=== STEP 3: Looking up game metadata ===")
game_info = lookup_game(GAME_ID, EMAIL, PASSWORD)
if not game_info.get("success"):
    print(f"  ERROR: {game_info.get('error')}")
    # Continue anyway — we have the URL
    game_info = {"game_id": GAME_ID, "vod_available": True}
else:
    print(f"  Home: {game_info.get('home_team')}")
    print(f"  Away: {game_info.get('away_team')}")
    print(f"  Date: {game_info.get('date')}")
    print(f"  Gender: {game_info.get('gender')}")
    print(f"  Level: {game_info.get('level')}")
    print(f"  VOD available: {game_info.get('vod_available')}")
    print(f"  Score: {game_info.get('score')}")
    print(f"  Headline: {game_info.get('headline')}")

# === STEP 4: Download video ===
print(f"\n=== STEP 4: Downloading video ===")
print(f"  URL: {GAME_URL}")
print(f"  Output: {OUTPUT_DIR}/nfhs_{GAME_ID}.mp4")

yt_dlp = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/.venv/bin/yt-dlp'
output_path = os.path.join(OUTPUT_DIR, f"nfhs_{GAME_ID}.%(ext)s")

cmd = [
    yt_dlp, '--no-check-certificates',
    '--add-header', f'Authorization: Bearer {token}',
    '--add-header', 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    '-f', 'best',
    '-o', output_path,
    '--merge-output-format', 'mp4',
    '--retries', '5',
    '--fragment-retries', '5',
    '--no-part',
    GAME_URL
]

print(f"  Running yt-dlp...")
sys.stdout.flush()

result = subprocess.run(cmd, capture_output=True, text=True)
rc = result.returncode
print(f"  RC: {rc}")

if result.stdout:
    print(f"  STDOUT (last 500 chars): {result.stdout[-500:]}")
if result.stderr:
    print(f"  STDERR (last 2000 chars): {result.stderr[-2000:]}")

sys.stdout.flush()

# === STEP 5: Check downloaded file ===
print(f"\n=== STEP 5: Checking downloaded files ===")
files = glob.glob(os.path.join(OUTPUT_DIR, f"nfhs_{GAME_ID}*"))
downloaded = [f for f in files if not f.endswith('.part') and not f.endswith('.ytdl')]

if downloaded:
    for f in sorted(downloaded):
        size = os.path.getsize(f)
        print(f"  File: {f} ({size/1024/1024:.1f} MB)")
        probe = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', f],
            capture_output=True, text=True)
        if probe.returncode == 0:
            info = json.loads(probe.stdout)
            for s in info.get('streams', []):
                if s.get('codec_type') == 'video':
                    print(f"    Video: {s['width']}x{s['height']}, codec={s['codec_name']}, fps={s.get('r_frame_rate', '?')}")
                    duration = s.get('duration', '?')
                    print(f"    Duration: {duration}s")
                elif s.get('codec_type') == 'audio':
                    print(f"    Audio: codec={s['codec_name']}, rate={s.get('sample_rate', '?')}")
else:
    print("  No complete download found")
    print(f"  Partial files: {files}")

print("\n=== DONE ===")
