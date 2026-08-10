"""Probe Copy to… endpoint and list HTML."""
import re
import requests

s = requests.Session()
r = s.get("http://127.0.0.1:8080/playbook?team=hs_boys", timeout=20)
print("list", r.status_code, "copy forms", len(re.findall(r"copy-to-team", r.text)))

# Find play ids + names from rows
rows = []
for m in re.finditer(
    r'data-play-id="(\d+)"[^>]*data-name="([^"]*)"|data-name="([^"]*)"[^>]*data-play-id="(\d+)"',
    r.text,
):
    if m.group(1):
        rows.append((m.group(1), m.group(2)))
    else:
        rows.append((m.group(4), m.group(3)))
print("sample rows", rows[:8])
game = next((pid for pid, name in rows if "1-game" in (name or "").lower()), None)
print("game_id", game)

m2 = re.search(r'action="(/playbook/play/(\d+)/copy-to-team)"', r.text)
pid = m2.group(2)
print("first_copy_pid", pid)

r2 = s.post(
    f"http://127.0.0.1:8080/playbook/play/{pid}/copy-to-team",
    data={"target_team": "hs_girls"},
    allow_redirects=True,
    timeout=20,
)
print("post", r2.status_code, "url", r2.url)
print("has Copied flash?", "Copied" in r2.text)
print("team label in page?", "High School Girls" in r2.text)

# Check selected option
sel = re.search(r'id="playbookTeamSelect"[\s\S]*?</select>', r2.text)
if sel:
    for o in re.findall(r'<option[^>]*value="([^"]+)"([^>]*)>', sel.group(0)):
        print(" option", o[0], "selected" if "selected" in o[1] else "")

# Check flash rendering in template path
print("alert-success?", "alert-success" in r2.text)
print("message block raw snippets:")
for m in re.finditer(r'class="alert[^"]*"[^>]*>[^<]{0,120}', r2.text):
    print(" ", m.group(0))

# Check team switcher JS for localStorage override
if "PLAYBOOK_TEAM_STORAGE_KEY" in r2.text:
    idx = r2.text.find("PLAYBOOK_TEAM_STORAGE_KEY")
    print("team js snippet:\n", r2.text[idx : idx + 800])
