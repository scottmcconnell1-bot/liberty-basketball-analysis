#!/usr/bin/env python3
"""Download 4K NFHS video for Liberty vs Riverstone game."""
import sys, os, glob, json, subprocess, sqlite3

sys.path.insert(0, '/home/monk-admin/PROJECTS/liberty-basketball-analysis')
from nfhs import get_nfhs_token, _decrypt_password

# Get credentials
db = sqlite3.connect('/home/monk-admin/PROJECTS/liberty-basketball-analysis/film_analysis.db')
row = db.execute("SELECT email, password_enc FROM nfhs_credentials WHERE is_active=1 ORDER BY id DESC LIMIT 1").fetchone()
db.close()

email, password_enc = row
password = _decrypt_password(password_enc)
access_token = get_nfhs_token(email, password)
print(f"Token OK: {access_token[:15]}...")

# Find yt-dlp
yt_dlp = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/.venv/bin/yt-dlp'
if not os.path.exists(yt_dlp):
    # fallback
    import shutil
    yt_dlp = shutil.which('yt-dlp')
    if not yt_dlp:
        print("ERROR: yt-dlp not found")
        sys.exit(1)

os.makedirs('videos', exist_ok=True)

cmd = [
    yt_dlp, '--no-check-certificates',
    '--add-header', f'Authorization: Bearer {access_token}',
    '--add-header', 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    '-f', 'best',
    '-o', '/home/monk-admin/PROJECTS/liberty-basketball-analysis/videos/nfhs_4K_gam021ddbf1cf.%(ext)s',
    '--merge-output-format', 'mp4',
    '--retries', '5',
    '--fragment-retries', '5',
    '--no-part',
    'https://www.nfhsnetwork.com/events/liberty-charter-school-nampa-id/gam021ddbf1cf'
]

print(f"Downloading with: {' '.join(cmd[:3])}...")
sys.stdout.flush()

result = subprocess.run(cmd, capture_output=True, text=True)
print(f"RC: {result.returncode}")
if result.stdout:
    print(f"STDOUT: {result.stdout[-500:]}")
if result.stderr:
    print(f"STDERR: {result.stderr[-3000:]}")
sys.stdout.flush()

# Check result
files = glob.glob('/home/monk-admin/PROJECTS/liberty-basketball-analysis/videos/nfhs_4K_*')
for f in sorted(files):
    if not f.endswith('.part') and not f.endswith('.ytdl'):
        size = os.path.getsize(f)
        print(f"\nFile: {f} ({size/1024/1024:.1f} MB)")
        probe = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', f],
            capture_output=True, text=True)
        if probe.returncode == 0:
            info = json.loads(probe.stdout)
            for s in info.get('streams', []):
                if s.get('codec_type') == 'video':
                    print(f"  Video: {s['width']}x{s['height']}, codec={s['codec_name']}, fps={s.get('r_frame_rate', '?')}")
                elif s.get('codec_type') == 'audio':
                    print(f"  Audio: codec={s['codec_name']}, rate={s.get('sample_rate', '?')}")
