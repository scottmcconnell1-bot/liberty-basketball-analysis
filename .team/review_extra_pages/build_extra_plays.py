"""Build the BLOB/SLOB, Press, Press Break and Transition plays for the public page
from the catalog drawings (Liberty_Play_Catalog/auto_choreography), the same source as
the 15 offense plays already on the page (Scott 2026-11-01: "Catalog drawings").

Page step format: {set, offense: {o1: {x, y}}, ball, paths: {o4: {type, via: [...]}}, defense?: {d1: {x, y}}}
Court: half court 500 x 470, basket at the top (y 15). Full court 500 x 940, top basket at y 15,
bottom basket at y 925. Half-court drawings on a full-court page sit in the top half as drawn.
"""
import json
import os
import sys

AUTO = "C:/Users/scott/Documents/Liberty_Play_Catalog/auto_choreography/"
EXTRACT = os.path.join(os.environ["TMP"], "plays.json")

PAGES = {
    "blob": [("p001_Box_1", "Box 1"), ("p004_Cross", "Cross"), ("p006_Flob", "Flob"),
             ("p008_Triangle", "Triangle"), ("p011_X", "X")],
    "press": [("p016_12", "12")],
    "pressbreak": [("p133_Man_4_across", "Man - 4 Across"), ("p136_Zone_Slash", "Zone - Slash")],
    "transition": [("p144_4_Flash", "4 Flash"), ("p150_5_1_2", "5-1-2"), ("p152_5_1_2_4", "5-1-2-4"),
                   ("p155_5_1_3", "5-1-3"), ("p157_Finish_the_Cycle", "Finish the Cycle"),
                   ("p163_Last_Leg", "Last Leg"), ("p170_Pitt_1", "Pitt 1"), ("p172_Pitt_5", "Pitt 5")],
}
FULL_FRAME_W = 0.5296   # court_frac width of a full-court (portrait) drawing
# Drawings whose defenders (x1..x5) were read from the PDF text: (extract name, page index).
DEFENSE_FROM = {"p016_12": ("12", 0), "p133_Man_4_across": ("Man - 4 across", 0)}


def r1(v):
    return round(float(v), 1)


def pt(p, full):
    return {"x": r1(p["x"]), "y": r1(p["y"] * 2 if full else p["y"])}


def thin(points, keep=3):
    inner = points[1:-1]
    if len(inner) <= keep:
        return inner
    step = (len(inner) - 1) / (keep - 1)
    return [inner[round(i * step)] for i in range(keep)]


def defense_spots(auto_name, step0_pos, full):
    if auto_name not in DEFENSE_FROM:
        return None
    name, idx = DEFENSE_FROM[auto_name]
    ex = json.load(open(EXTRACT))["white"]
    page = [e for e in ex if e["name"] == name][0]["pages"][idx]["pos"]
    # Fit page = a*u + b (x) and c*v + d (y) on the offense numbers both sources have.
    pairs = [(page[k], step0_pos["o" + k]) for k in "12345" if k in page and "o" + k in step0_pos]
    def fit(us, ps):
        n = len(us); mu, mp = sum(us) / n, sum(ps) / n
        a = sum((u - mu) * (p - mp) for u, p in zip(us, ps)) / sum((u - mu) ** 2 for u in us)
        return a, mp - a * mu
    ax, bx = fit([u for (u, _v), _ in pairs], [p["x"] for _, p in pairs])
    ay, by = fit([v for (_u, v), _ in pairs], [p["y"] for _, p in pairs])
    out = {}
    for k in "12345":
        if "x" + k in page:
            u, v = page["x" + k]
            out["d" + k] = pt({"x": ax * u + bx, "y": ay * v + by}, full)
    return out


def convert(auto_name, name):
    d = json.load(open(AUTO + auto_name + ".json", encoding="utf-8"))
    st = d["steps"]
    full = abs(st[0]["court_frac"]["w"] - FULL_FRAME_W) < 0.01
    passes = [m for s in st for m in s.get("movements", []) if m["type"] == "pass" and m.get("to") != m.get("from")]
    ball = passes[0]["from"] if passes else "o1"
    cur = {k: pt(v, full) for k, v in st[0]["positions"].items()}
    steps = [{"set": "4o1i", "offense": dict(cur), "ball": ball}]
    defense = defense_spots(auto_name, st[0]["positions"], full)
    if defense:
        steps[0]["defense"] = defense
    for k in range(1, len(st) + 1):
        moves = st[k - 1].get("movements", [])
        nxt = st[k]["positions"] if k < len(st) else None
        if nxt is None and not any(m["type"] != "pass" for m in moves) and not any(
                m["type"] == "pass" and m.get("to") != m.get("from") for m in moves):
            break
        off, paths = dict(cur), {}
        if nxt:   # everyone the next drawing shows moves to its spot
            for o, p in nxt.items():
                off[o] = pt(p, full)
        for m in moves:
            if m["type"] == "pass":
                if m.get("to") and m["to"] != m["from"]:
                    ball = m["to"]
                continue
            o = m["from"]
            pts = [pt(p, full) for p in m["points"]]
            if not nxt or o not in nxt:
                off[o] = pts[-1]
            paths[o] = {"type": m["type"], "via": thin(pts)}
        step = {"set": "4o1i", "offense": off, "ball": ball}
        if paths:
            step["paths"] = paths
        if off == cur and not paths and ball == steps[-1]["ball"]:
            continue   # nothing moved
        steps.append(step)
        cur = off
    for s in steps:   # a player missing from a drawing keeps his last spot
        for o in list(steps[0]["offense"]):
            pass
    return {"name": name, "court": "full" if full else "half", "steps": steps}


def main():
    out = {page: [convert(a, n) for a, n in plays] for page, plays in PAGES.items()}
    # Fill players a drawing left out with their last known spot so all 5 show every step.
    for plays in out.values():
        for p in plays:
            last = {}
            for s in p["steps"]:
                for o, q in s["offense"].items():
                    last[o] = q
            seen = {}
            for s in p["steps"]:
                seen.update(s["offense"])
                for o in seen:
                    s["offense"].setdefault(o, seen[o])
    json.dump(out, open(sys.argv[1], "w"), indent=1)
    for page, plays in out.items():
        for p in plays:
            print(page, p["name"], p["court"], "steps", len(p["steps"]) - 1,
                  "players", [len(s["offense"]) for s in p["steps"]],
                  "lines", [len(s.get("paths", {})) for s in p["steps"]],
                  "def" if p["steps"][0].get("defense") else "")


if __name__ == "__main__":
    main()
