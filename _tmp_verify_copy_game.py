"""Verify Copy to… flash + redirect and 1-Game live page."""
import re
import time
import requests

s = requests.Session()
ts = int(time.time())

r = s.get(f"http://127.0.0.1:8080/playbook?team=hs_boys&_={ts}", timeout=30)
assert r.status_code == 200
assert "play-copy-to-team" in r.text
assert 'value=""' in r.text
assert "get_flashed_messages" in open(
    r"C:\Users\scott\Documents\liberty-basketball-analysis\templates\playbook.html",
    encoding="utf-8",
).read()
print("LIST_OK forms=", r.text.count("copy-to-team"))

# Find a top-level play id (1-2-2)
m = re.search(r'data-play-id="(\d+)"[^>]*data-name="1-2-2"', r.text)
if not m:
    m = re.search(r'data-name="1-2-2"[^>]*data-play-id="(\d+)"', r.text)
pid = m.group(1) if m else None
print("PID", pid)
assert pid

r2 = s.post(
    f"http://127.0.0.1:8080/playbook/play/{pid}/copy-to-team",
    data={"target_team": "jh_girls"},
    allow_redirects=False,
    timeout=30,
)
print("REDIR", r2.status_code, r2.headers.get("Location"))
assert r2.status_code in (301, 302)
assert "team=jh_girls" in (r2.headers.get("Location") or "")
assert "copied=" in (r2.headers.get("Location") or "")

r3 = s.get("http://127.0.0.1:8080" + r2.headers["Location"], timeout=30)
print("FLASH", "Copied" in r3.text, "alert-success count", r3.text.count("alert-success"))
assert "Copied" in r3.text
assert "Jr High Girls" in r3.text

# empty rejected
r4 = s.post(
    f"http://127.0.0.1:8080/playbook/play/{pid}/copy-to-team",
    data={"target_team": ""},
    allow_redirects=True,
    timeout=30,
)
assert "Pick a team" in r4.text
print("EMPTY_REJECT_OK")

# 1-Game page
r5 = s.get(f"http://127.0.0.1:8080/playbook/play/98?_={ts}", timeout=60)
print("GAME98", r5.status_code, "len", len(r5.text))
assert r5.status_code == 200
assert "isGamePlay" in r5.text
assert "animateParallelPaths" in r5.text
assert "game-open-pop" in r5.text
print("GAME98_JS_OK")
print("LIVE_PROOF_OK")
