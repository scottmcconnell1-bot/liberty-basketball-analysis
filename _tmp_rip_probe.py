import json
import urllib.request

play = json.load(urllib.request.urlopen("http://127.0.0.1:8080/api/playbook/play/125"))
p = play["play"]
print("play name:", p.get("name"))
steps = p.get("steps") or []
print("n_steps", len(steps))
for i, s in enumerate(steps):
    print("--- step", i, "---")
    print("label:", s.get("label"))
    print("source_image:", s.get("source_image"))
    print("ball:", s.get("ball"))
    pos = s.get("positions") or {}
    if isinstance(pos, str):
        pos = json.loads(pos)
    for k in sorted(pos.keys()):
        if str(k).startswith("o"):
            v = pos[k]
            print(f"  {k}: ({v.get('x'):.1f},{v.get('y'):.1f})" if isinstance(v, dict) else f"  {k}: {v}")
    moves = s.get("movements") or []
    if isinstance(moves, str):
        moves = json.loads(moves)
    print("movements:", moves)

# Also try sheet-align endpoint for positions
for i, s in enumerate(steps):
    img = s.get("source_image")
    if not img:
        continue
    body = json.dumps({"image_url": img}).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:8080/api/playbook/sheet-align",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        align = json.load(urllib.request.urlopen(req))
        print(f"\n=== align step {i} ===")
        print("ok", align.get("ok"), "keys", list(align.keys())[:12])
        pos = align.get("positions") or {}
        for k in sorted(pos.keys()):
            if str(k).startswith("o"):
                v = pos[k]
                print(f"  {k}: ({v.get('x'):.1f},{v.get('y'):.1f})")
    except Exception as e:
        print("align err", i, e)
