import json
import urllib.request

BASE = "http://127.0.0.1:8080"
raw = json.load(urllib.request.urlopen(f"{BASE}/api/playbook/play/125"))
steps = raw["steps"]

aligns = []
for i, s in enumerate(steps):
    body = json.dumps({"image_url": s["source_image"]}).encode()
    req = urllib.request.Request(
        f"{BASE}/api/playbook/sheet-align",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    align = json.load(urllib.request.urlopen(req))
    pos = align.get("positions") or {}
    print(f"\n=== ALIGN step {i} page {s['source_image'].split('/')[-1]} ===")
    print("ok", align.get("ok"))
    for k in sorted(pos.keys()):
        if str(k).startswith("o") and isinstance(pos[k], dict):
            print(f"  {k}: ({pos[k]['x']:.1f}, {pos[k]['y']:.1f})")
    aligns.append(pos)

# Sheet paths for each step using same-sheet from/to (as Play All last sheet does)
for i, s in enumerate(steps):
    from_pos = aligns[i]
    to_pos = aligns[i]  # same sheet ink discovery
    body = json.dumps({
        "image_url": s["source_image"],
        "from_positions": {k: {"x": v["x"], "y": v["y"]} for k, v in from_pos.items() if str(k).startswith("o")},
        "to_positions": {k: {"x": v["x"], "y": v["y"]} for k, v in to_pos.items() if str(k).startswith("o")},
    }).encode()
    req = urllib.request.Request(
        f"{BASE}/api/playbook/sheet-paths",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    data = json.load(urllib.request.urlopen(req))
    print(f"\n=== PATHS step {i} ===")
    print("ok", data.get("ok"))
    marks = data.get("marks") or {}
    paths = data.get("paths") or {}
    passes = data.get("passes") or []
    print("marks", marks)
    for pid, poly in paths.items():
        if not poly:
            continue
        a, b = poly[0], poly[-1]
        plen = 0
        for j in range(1, len(poly)):
            plen += ((poly[j]["x"] - poly[j-1]["x"]) ** 2 + (poly[j]["y"] - poly[j-1]["y"]) ** 2) ** 0.5
        print(f"  path {pid}: n={len(poly)} start=({a['x']:.1f},{a['y']:.1f}) end=({b['x']:.1f},{b['y']:.1f}) len={plen:.1f} mark={marks.get(pid)}")
    for p in passes:
        pts = p.get("points") or []
        a = pts[0] if pts else {}
        b = pts[-1] if pts else {}
        print(f"  pass {p.get('fromPid')}->{p.get('toPid')} orphan={p.get('orphan')} n={len(pts)} "
              f"({a.get('x',0):.1f},{a.get('y',0):.1f})->({b.get('x',0):.1f},{b.get('y',0):.1f})")

# Also transition paths step1->step2 and step2->step3 using next sheet OCR as to
for i in range(len(steps) - 1):
    from_pos = aligns[i]
    to_pos = aligns[i + 1]
    # merge missing
    merged_to = dict(from_pos)
    merged_to.update(to_pos)
    body = json.dumps({
        "image_url": steps[i]["source_image"],
        "from_positions": {k: {"x": v["x"], "y": v["y"]} for k, v in from_pos.items() if str(k).startswith("o")},
        "to_positions": {k: {"x": v["x"], "y": v["y"]} for k, v in merged_to.items() if str(k).startswith("o")},
    }).encode()
    req = urllib.request.Request(
        f"{BASE}/api/playbook/sheet-paths",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    data = json.load(urllib.request.urlopen(req))
    print(f"\n=== TRANSITION paths sheet{i}->sheet{i+1} ===")
    print("marks", data.get("marks"))
    for pid, poly in (data.get("paths") or {}).items():
        a, b = poly[0], poly[-1]
        print(f"  {pid}: ({a['x']:.1f},{a['y']:.1f})->({b['x']:.1f},{b['y']:.1f})")
    for p in data.get("passes") or []:
        print(f"  pass {p.get('fromPid')}->{p.get('toPid')} orphan={p.get('orphan')}")
