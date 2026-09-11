import json, sqlite3, subprocess, sys
from pathlib import Path
ROOT = Path('.').resolve()
PY = sys.executable
DB = ROOT / 'film_analysis.db'
c = sqlite3.connect(str(DB))
keys = [r[0] for r in c.execute(
    """SELECT DISTINCT game_id FROM detections
       WHERE game_id LIKE 'hoopsalytics%' ORDER BY game_id"""
)]
c.close()
print(f"regenerating {len(keys)} keys with new calibrator...")
for i, key in enumerate(keys, 1):
    print(f"[{i}/{len(keys)}] {key}", flush=True)
    rc = subprocess.call([PY, 'scripts/regenerate_events.py', key], cwd=str(ROOT))
    print(f"  rc={rc}", flush=True)

GAMES = [
    ("hoopsalytics-marsing-2025-12-02", "hoopsalytics_marsing_2025-12-02", "Marsing"),
    ("hoopsalytics-nyssa-2025-12-04", "hoopsalytics_nyssa_2025-12-04", "Nyssa"),
    ("hoopsalytics-harper_or-2025-12-05", "hoopsalytics_harper_or_2025-12-05", "Harper"),
    ("hoopsalytics-burns_or-2025-12-06", "hoopsalytics_burns_or_2025-12-06", "Burns"),
    ("hoopsalytics-melba-2025-12-09", "hoopsalytics_melba_2025-12-09", "Melba"),
    ("hoopsalytics-camas_county-2025-12-13", "hoopsalytics_camas_county_2025-12-13", "Camas"),
    ("hoopsalytics-idaho_city-2026-01-05", "hoopsalytics_idaho_city_2026-01-05", "Idaho City"),
    ("hoopsalytics-north_star_charter-2026-01-08", "hoopsalytics_north_star_charter_2026-01-08", "North Star"),
    ("hoopsalytics-grace-2026-01-10", "hoopsalytics_grace_2026-01-10", "Grace"),
]
# Prefer best analysis key per base (max dets)
c = sqlite3.connect(str(DB))
scores = []
taught = []
for film, base, name in GAMES:
    row = c.execute(
        """SELECT game_id FROM detections
           WHERE game_id=? OR game_id LIKE ?
           GROUP BY game_id ORDER BY COUNT(*) DESC LIMIT 1""",
        (base, base + '__rerun_%'),
    ).fetchone()
    key = row[0] if row else base
    print(f"score {name} key={key}", flush=True)
    subprocess.call([PY, 'scripts/compare_ai_to_hoops_pbp.py', '--film-id', film, '--analysis-key', key], cwd=str(ROOT))
    score_path = ROOT / 'data' / 'hoopsalytics' / f"compare_{film.replace('-', '_')}.json"
    score = {'name': name, 'key': key}
    if score_path.exists():
        score.update(json.loads(score_path.read_text(encoding='utf-8')))
    print(f"  prec={score.get('precision')} rec={score.get('recall')} exact={score.get('exact')} miss={score.get('miss')} extra={score.get('extra')}", flush=True)
    scores.append(score)
    taught.append(key)
    taught.append(base)
c.close()
state = {'taught_keys': sorted(set(taught)), 'scores': scores, 'note': 'rescored 2026-07-26 after zombie fix + recalibrate'}
(ROOT/'data'/'hoopsalytics'/'teach_loop_state.json').write_text(json.dumps(state, indent=2), encoding='utf-8')
print('DONE rescore')
