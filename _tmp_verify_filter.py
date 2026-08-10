import urllib.request
import re

for team in ("hs_boys", "hs_girls", "jh_boys"):
    html = urllib.request.urlopen(
        f"http://127.0.0.1:8080/playbook?team={team}"
    ).read().decode("utf-8", "replace")
    ids = re.findall(r'data-play-id="(\d+)"', html)
    items = html.count("play-list-item play-row")
    has_pitt_row = 'data-name="' in html and "pitt 5" in html.lower()
    # More precise: play title containing Pitt 5 inside list
    pitt_in_list = bool(re.search(r'play-list-item-title[^>]*>\s*Pitt 5\s*<', html)) or (
        'data-name="pitt 5' in html.lower()
    )
    print(
        team,
        "unique_ids",
        len(set(ids)),
        "items",
        items,
        "pitt_in_list",
        pitt_in_list,
        "selected",
        f'value="{team}" selected' in html or f"value='{team}' selected" in html,
    )
