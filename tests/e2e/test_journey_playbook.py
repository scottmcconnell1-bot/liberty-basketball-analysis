"""Playbook journeys through the HTTP routes, asserting exact rows / step order / JSON.

Covers: play CRUD, category tree + moves/reorders/progressions, duplicate + copy-to-team,
share links and view/edit/share controls, PDF + bulk import, sticky choreography, play-match
for a game, opponent playbooks. Known bugs are kept as strict xfails asserting the correct
behaviour.

Everything writes to the per-test temp DB / UPLOAD_FOLDER / tmp_path (choreography and
play-match stores are monkeypatched), never into the repo tree.
"""
from __future__ import annotations

import io
import json
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from tests.e2e import data as td

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")


# ── helpers ──────────────────────────────────────────────────────────────────


@pytest.fixture
def db(app):
    """Own connection to the test DB (overrides tests/conftest.py's `db`).

    The shared fixture pushes an app context, which makes every test-client request reuse
    one connection and one `g` (cached feature flags, uncommitted writes of refused
    requests). A separate connection keeps requests isolated like in production.
    """
    conn = sqlite3.connect(app.config["DATABASE"], timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


@pytest.fixture
def choreo_base(tmp_path, monkeypatch):
    """Point playbook + play-match choreography reads/writes at tmp."""
    from blueprints import ai as ai_mod
    from blueprints import playbook as pb

    base = tmp_path / "playbook_data"
    base.mkdir()
    monkeypatch.setattr(pb, "_choreography_base", lambda: base)
    monkeypatch.setattr(ai_mod, "_choreography_match_base", lambda: str(base))
    return base


def _flat(client):
    r = client.get("/api/playbook/categories")
    assert r.status_code == 200
    return r.get_json()["flat"]


def _cat(client, slug_path):
    for c in _flat(client):
        if c["slug_path"] == slug_path:
            return c
    raise AssertionError(f"category {slug_path!r} not found")


def _tree_node(tree, cat_id):
    stack = list(tree)
    while stack:
        n = stack.pop()
        if n["id"] == cat_id:
            return n
        stack.extend(n.get("children") or [])
    return None


def _tree_ids(tree):
    out, stack = [], list(tree)
    while stack:
        n = stack.pop()
        out.append(n["id"])
        stack.extend(n.get("children") or [])
    return out


def _save_play(client, **fields):
    data = {
        "name": "Play",
        "description": "",
        "tags": "",
        "diagram_json": "{}",
        "steps_json": "[]",
    }
    data.update({k: (json.dumps(v) if k == "steps_json" and not isinstance(v, str) else v)
                 for k, v in fields.items()})
    r = _post(client, "/playbook/save", data=data)
    assert r.status_code == 302, r.data[:300]
    m = re.search(r"/playbook/play/(\d+)$", r.headers["Location"])
    assert m, r.headers["Location"]
    return int(m.group(1))


def _post(client, url, **kw):
    return client.post(url, follow_redirects=False, **kw)


def _api_play(client, play_id):
    r = client.get(f"/api/playbook/play/{play_id}")
    assert r.status_code == 200, r.data[:300]
    return r.get_json()


def _steps(client, play_id):
    return [
        {
            "step_number": s["step_number"],
            "label": s["label"],
            "positions": json.loads(s["positions_json"]),
            "movements": json.loads(s["movements_json"]),
            "notes": s["notes"],
            "source_image": s["source_image"],
        }
        for s in _api_play(client, play_id)["steps"]
    ]


def _count(db, sql, *params):
    return db.execute(sql, params).fetchone()[0]


def _js_function(source: str, name: str) -> str:
    """Return the full text of `function name(...) {...}` from a JS/HTML source."""
    m = re.search(r"(?:async\s+)?function\s+" + re.escape(name) + r"\s*\(", source)
    assert m, f"{name} not found"
    i = source.index("{", m.end())
    depth = 0
    for j in range(i, len(source)):
        if source[j] == "{":
            depth += 1
        elif source[j] == "}":
            depth -= 1
            if depth == 0:
                return source[m.start(): j + 1]
    raise AssertionError(f"unbalanced braces in {name}")


def _run_node(script: str):
    if not NODE:
        pytest.skip("node not available")
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


STEPS_3 = [
    {
        "label": "Initial",
        "positions": {"o1": {"x": 250, "y": 380}, "o2": {"x": 150, "y": 320},
                      "o3": {"x": 350, "y": 320}, "d1": {"x": 250, "y": 340}},
        "movements": [{"from": "o1", "to": "o2", "type": "pass", "timing": "sync"}],
        "notes": "1 passes to 2",
        "source_image": "",
        "ball": "o1",
    },
    {
        "label": "Flare",
        "positions": {"o1": {"x": 250, "y": 380}, "o2": {"x": 120, "y": 300},
                      "o3": {"x": 380, "y": 300}},
        "movements": [
            {"from": "o3", "to": "o3", "type": "cut", "timing": "sync",
             "points": [{"x": 380, "y": 300}, {"x": 400, "y": 250}]},
            {"from": "o4", "to": "o4", "type": "screen", "timing": "optional"},
        ],
        "notes": "",
        "source_image": "/uploads/play_imports/sheet2.png",
        "ball": "o2",
    },
    {
        "label": "Finish",
        "positions": {"o2": {"x": 100, "y": 100}},
        "movements": [],
        "notes": "shot",
        "source_image": "",
    },
]


# ── 1. play CRUD ─────────────────────────────────────────────────────────────


def test_play_create_reload_edit_delete(client, db):
    man = _cat(client, "offense/man")
    pid = _save_play(
        client, name="Horns Flare", description="wing entry", category_id=str(man["id"]),
        tags="horns, flare", diagram_json=json.dumps({"court": "half"}), steps_json=STEPS_3,
        team_key="hs_girls",
    )

    data = _api_play(client, pid)
    play = data["play"]
    assert (play["name"], play["description"], play["tags"], play["team_key"]) == (
        "Horns Flare", "wing entry", "horns, flare", "hs_girls")
    assert play["category_id"] == man["id"] and play["category"] == "offense"
    assert json.loads(play["diagram_json"]) == {"court": "half"}
    assert play["share_token"] is None

    steps = _steps(client, pid)
    assert [s["step_number"] for s in steps] == [0, 1, 2]
    assert [s["label"] for s in steps] == ["Initial", "Flare", "Finish"]
    assert [s["positions"] for s in steps] == [s["positions"] for s in STEPS_3]
    # The carried ball is stored as one trailing _meta entry; steps without ball have none.
    assert steps[0]["movements"] == STEPS_3[0]["movements"] + [{"_meta": True, "_ball": "o1"}]
    assert steps[1]["movements"] == STEPS_3[1]["movements"] + [{"_meta": True, "_ball": "o2"}]
    assert steps[2]["movements"] == []
    assert [s["notes"] for s in steps] == ["1 passes to 2", "", "shot"]
    assert steps[1]["source_image"] == "/uploads/play_imports/sheet2.png"

    # Export is the same document as the API.
    exp = client.get(f"/playbook/export/{pid}")
    assert exp.status_code == 200
    assert f"play_{pid}.json" in exp.headers["Content-Disposition"]
    assert json.loads(exp.data) == data

    # Team scoping on the list page.
    assert "Horns Flare" in client.get("/playbook?team=hs_girls").get_data(as_text=True)
    assert "Horns Flare" not in client.get("/playbook?team=hs_boys").get_data(as_text=True)

    # Edit: re-save loaded steps (movements incl. _meta) + ball, reorder, drop one.
    loaded = _steps(client, pid)
    new_steps = [
        {"label": "Flare v2", "positions": loaded[1]["positions"],
         "movements": loaded[1]["movements"], "ball": "o3", "notes": "n2",
         "source_image": loaded[1]["source_image"]},
        {"label": "Initial v2", "positions": loaded[0]["positions"],
         "movements": loaded[0]["movements"], "notes": "", "source_image": ""},
    ]
    assert _save_play(client, play_id=str(pid), name="Horns Flare 2",
                      category_id=str(man["id"]), steps_json=new_steps) == pid
    assert _count(db, "SELECT COUNT(*) FROM plays") == 1
    assert _count(db, "SELECT COUNT(*) FROM play_steps WHERE play_id=?", pid) == 2
    steps = _steps(client, pid)
    assert [s["label"] for s in steps] == ["Flare v2", "Initial v2"]
    assert [s["step_number"] for s in steps] == [0, 1]
    # Old ball meta replaced, not duplicated.
    assert steps[0]["movements"] == STEPS_3[1]["movements"] + [{"_meta": True, "_ball": "o3"}]
    assert steps[1]["movements"] == STEPS_3[0]["movements"] + [{"_meta": True, "_ball": "o1"}]
    play = _api_play(client, pid)["play"]
    assert play["name"] == "Horns Flare 2"
    assert play["team_key"] == "hs_girls"  # form without team_key keeps the play's team

    # Delete removes play + steps.
    r = _post(client, f"/playbook/play/{pid}/delete")
    assert r.status_code == 302 and "team=hs_girls" in r.headers["Location"]
    assert client.get(f"/api/playbook/play/{pid}").status_code == 404
    assert _count(db, "SELECT COUNT(*) FROM play_steps WHERE play_id=?", pid) == 0


def test_save_without_name_creates_nothing(client, db):
    r = _post(client, "/playbook/save", data={"name": "  ", "steps_json": json.dumps(STEPS_3)})
    assert r.status_code == 302
    assert _count(db, "SELECT COUNT(*) FROM plays") == 0
    assert _count(db, "SELECT COUNT(*) FROM play_steps") == 0


# ── 2. categories / taxonomy / ordering ──────────────────────────────────────


def _create_cat(client, parent_id, name):
    r = client.post("/api/playbook/categories", json={"parent_id": parent_id, "name": name})
    assert r.status_code == 200, r.data
    return r.get_json()["id"]


def test_category_tree_moves_reorders_and_progressions(client, db):
    man = _cat(client, "offense/man")
    sets_id = _create_cat(client, man["id"], "Sets")
    horns_id = _create_cat(client, sets_id, "Horns")
    # duplicate name at the same level is rejected
    r = client.post("/api/playbook/categories", json={"parent_id": sets_id, "name": "Horns"})
    assert r.status_code == 400

    tree = client.get("/api/playbook/categories").get_json()["tree"]
    sets_node = _tree_node(tree, sets_id)
    assert sets_node["slug_path"] == "offense/man/sets"
    assert [c["id"] for c in sets_node["children"]] == [horns_id]
    assert _tree_node(tree, horns_id)["slug_path"] == "offense/man/sets/horns"
    assert sets_id in [c["id"] for c in _tree_node(tree, man["id"])["children"]]

    a = _save_play(client, name="Alpha", category_id=str(man["id"]), steps_json=STEPS_3[:1])
    b = _save_play(client, name="Bravo", category_id=str(man["id"]), steps_json=STEPS_3[:1])
    c = _save_play(client, name="Charlie", category_id=str(man["id"]))
    # progressions of Alpha
    p1 = _save_play(client, name="Alpha opt 1", category_id=str(man["id"]))
    p2 = _save_play(client, name="Alpha opt 2", category_id=str(man["id"]))
    p3 = _save_play(client, name="Alpha opt 3", category_id=str(man["id"]))
    for order, pid in enumerate((p1, p2, p3)):
        db.execute("UPDATE plays SET parent_play_id=?, progression_order=? WHERE id=?", (a, order, pid))
    db.commit()

    # Move to a parent folder is refused; to the leaf succeeds and progressions follow.
    r = client.post("/api/playbook/move-category", json={"play_ids": [a], "category_id": sets_id})
    assert r.status_code == 400
    r = client.post("/api/playbook/move-category", json={"play_ids": [a, b, p1], "category_id": horns_id})
    assert r.status_code == 200
    body = r.get_json()
    assert body["moved_ids"] == [a, b]  # p1 is a progression → skipped directly
    assert body["category_path"] == "offense/man/sets/horns"
    rows = dict(db.execute("SELECT id, category_id FROM plays").fetchall())
    assert {pid: rows[pid] for pid in (a, b, p1, p2, p3)} == dict.fromkeys((a, b, p1, p2, p3), horns_id)
    assert rows[c] == man["id"]
    assert db.execute("SELECT DISTINCT category FROM plays WHERE category_id=?", (horns_id,)).fetchall()[0][0] == "offense"
    horns_node = _tree_node(body["tree"], horns_id)
    sets_node = _tree_node(body["tree"], sets_id)
    assert horns_node["direct_play_count"] == 5 and sets_node["play_count"] == 5

    # Progression reorder via API, then up/down buttons.
    r = client.post("/api/playbook/reorder", json={"ordered_ids": [p3, p1, p2], "parent_play_id": a})
    assert r.status_code == 200
    order = lambda: [r_[0] for r_ in db.execute(  # noqa: E731
        "SELECT id FROM plays WHERE parent_play_id=? ORDER BY progression_order", (a,)).fetchall()]
    assert order() == [p3, p1, p2]
    assert _post(client, f"/playbook/play/{p2}/progression-move", data={"direction": "up"}).status_code == 302
    assert order() == [p3, p2, p1]
    _post(client, f"/playbook/play/{p3}/progression-move", data={"direction": "up"})  # already first
    assert order() == [p3, p2, p1]
    # A play from another group / a progression in a top-level reorder is refused.
    assert client.post("/api/playbook/reorder", json={"ordered_ids": [p1, b], "parent_play_id": a}).status_code == 400
    assert client.post("/api/playbook/reorder", json={"ordered_ids": [a, p1]}).status_code == 400
    assert order() == [p3, p2, p1]  # a refused reorder leaves no partial writes
    r = client.post("/api/playbook/reorder", json={"ordered_ids": [c, b, a]})
    assert r.status_code == 200
    assert [x[0] for x in db.execute(
        "SELECT id FROM plays WHERE parent_play_id IS NULL ORDER BY list_order").fetchall()] == [c, b, a]

    # View page of a progression shows the chip bar in progression order.
    html = client.get(f"/playbook/play/{p1}").get_data(as_text=True)
    chips = re.findall(r'play-progression-chip[^"]*"\s+href="/playbook/play/(\d+)"', html)
    assert [int(x) for x in chips] == [a, p3, p2, p1]

    # Delete: refused while it has plays and no target, then reassigns.
    r = client.delete(f"/api/playbook/categories/{horns_id}", json={})
    assert r.status_code == 400
    assert client.delete(f"/api/playbook/categories/{man['id']}", json={}).status_code == 400  # system
    r = client.delete(f"/api/playbook/categories/{horns_id}", json={"reassign_to": man["id"]})
    assert r.status_code == 200
    assert _count(db, "SELECT COUNT(*) FROM plays WHERE category_id=?", man["id"]) == 6
    assert horns_id not in _tree_ids(r.get_json()["tree"])


def test_category_move_under_own_child_is_refused(client, db):
    man = _cat(client, "offense/man")
    sets_id = _create_cat(client, man["id"], "Sets")
    horns_id = _create_cat(client, sets_id, "Horns")
    r = client.post(f"/api/playbook/categories/{sets_id}/move", json={"parent_id": horns_id})
    tree = client.get("/api/playbook/categories").get_json()["tree"]
    # Whatever the response, both categories must stay reachable from a root.
    assert {sets_id, horns_id} <= set(_tree_ids(tree))
    assert r.status_code == 400


def test_category_move_to_top_level(client, db):
    man = _cat(client, "offense/man")
    sets_id = _create_cat(client, man["id"], "Sets")
    r = client.post(f"/api/playbook/categories/{sets_id}/move", json={"parent_id": None})
    assert r.status_code == 200
    row = db.execute("SELECT parent_id, slug_path FROM play_categories WHERE id=?", (sets_id,)).fetchone()
    assert (row["parent_id"], row["slug_path"]) == (None, "sets")


def test_category_rename_and_move_keep_descendant_paths(client, db):
    man = _cat(client, "offense/man")
    dman = _cat(client, "defense/man")
    sets_id = _create_cat(client, man["id"], "Sets")
    horns_id = _create_cat(client, sets_id, "Horns")
    pid = _save_play(client, name="H1", category_id=str(man["id"]))
    client.post("/api/playbook/move-category", json={"play_ids": [pid], "category_id": horns_id})

    assert client.put(f"/api/playbook/categories/{sets_id}", json={"name": "Actions"}).status_code == 200
    assert client.post(f"/api/playbook/categories/{sets_id}/move", json={"parent_id": dman["id"]}).status_code == 200
    path = db.execute("SELECT slug_path FROM play_categories WHERE id=?", (horns_id,)).fetchone()[0]
    # A fresh Sets/Horns under Offense/Man must not collide with the moved subtree.
    new_sets = _create_cat(client, man["id"], "Sets")
    r = client.post("/api/playbook/categories", json={"parent_id": new_sets, "name": "Horns"})
    assert path == "defense/man/actions/horns"
    assert r.status_code == 200
    # Plays saved into the moved leaf should now be defense plays.
    _save_play(client, play_id=str(pid), name="H1", category_id=str(horns_id))
    assert db.execute("SELECT category FROM plays WHERE id=?", (pid,)).fetchone()[0] == "defense"


def test_category_chip_after_drag_does_not_inject_html(client, db):
    man = _cat(client, "offense/man")
    evil = _create_cat(client, man["id"], "<img src=x onerror=alert(1)>")
    pid = _save_play(client, name="Victim", category_id=str(man["id"]))
    body = client.post("/api/playbook/move-category",
                       json={"play_ids": [pid], "category_id": evil}).get_json()
    # Layer 1: the server strips tag characters from category names.
    assert "<" not in body["category_path"] and ">" not in body["category_path"]
    # Layer 2: the chip escapes whatever path it is given (e.g. rows created before the
    # server-side stripping existed).
    body["category_path"] = "offense/man/<img src=x onerror=alert(1)>"
    src = (ROOT / "static/js/playbook-dnd.js").read_text()
    fn = _js_function(src, "updateCategoryChip")
    script = fn + """
const chip = {innerHTML: '', title: ''};
const row = {querySelector: () => chip};
updateCategoryChip(row, %s);
console.log(JSON.stringify(chip.innerHTML));
""" % json.dumps(body["category_path"])
    html = _run_node(script)
    assert "<img" not in html


# ── 3. duplicate + copy-to-team ──────────────────────────────────────────────


def test_duplicate_and_copy_to_team_are_independent_deep_copies(client, db):
    man = _cat(client, "offense/man")
    src = _save_play(client, name="Box Zipper", description="d", tags="box",
                     category_id=str(man["id"]), steps_json=STEPS_3, team_key="hs_boys")
    child = _save_play(client, name="Box opt", category_id=str(man["id"]),
                       steps_json=STEPS_3[2:], team_key="hs_boys")
    db.execute("UPDATE plays SET parent_play_id=?, progression_order=0 WHERE id=?", (src, child))
    db.commit()
    token = client.post(f"/api/playbook/play/{src}/share").get_json()["token"]
    src_steps = _steps(client, src)

    r = _post(client, f"/playbook/play/{src}/duplicate")
    assert r.status_code == 302
    dup = int(re.search(r"/playbook/play/(\d+)/edit$", r.headers["Location"]).group(1))
    d = _api_play(client, dup)["play"]
    assert (d["name"], d["team_key"], d["share_token"], d["parent_play_id"]) == (
        "Box Zipper (copy)", "hs_boys", None, None)
    assert (d["description"], d["tags"], d["category_id"]) == ("d", "box", man["id"])
    assert _steps(client, dup) == src_steps
    dup_children = db.execute("SELECT id, name FROM plays WHERE parent_play_id=?", (dup,)).fetchall()
    assert [r_["name"] for r_ in dup_children] == ["Box opt (copy)"]
    assert _steps(client, dup_children[0]["id"]) == _steps(client, child)

    # Editing the copy leaves the original alone (no shared step rows).
    _save_play(client, play_id=str(dup), name="Box Zipper (copy)", category_id=str(man["id"]),
               steps_json=[{"label": "only", "positions": {"o1": {"x": 1, "y": 2}}}])
    assert len(_steps(client, dup)) == 1
    assert _steps(client, src) == src_steps
    assert _post(client, f"/playbook/play/{dup_children[0]['id']}/delete").status_code == 302
    assert len(_steps(client, child)) == 1

    # Copy to another team: same name, target team, children too, token not copied.
    r = _post(client, f"/playbook/play/{src}/copy-to-team", data={"target_team": "hs_girls"})
    assert r.status_code == 302 and "team=hs_girls" in r.headers["Location"]
    copied = int(re.search(r"copied=(\d+)", r.headers["Location"]).group(1))
    c = _api_play(client, copied)["play"]
    assert (c["name"], c["team_key"], c["share_token"]) == ("Box Zipper", "hs_girls", None)
    assert _steps(client, copied) == src_steps
    kids = db.execute("SELECT id, name, team_key FROM plays WHERE parent_play_id=?", (copied,)).fetchall()
    assert [(k["name"], k["team_key"]) for k in kids] == [("Box opt", "hs_girls")]
    girls = client.get("/playbook?team=hs_girls").get_data(as_text=True)
    assert "Box Zipper" in girls
    assert db.execute("SELECT share_token FROM plays WHERE id=?", (src,)).fetchone()[0] == token

    # Unknown / missing team → nothing created.
    before = _count(db, "SELECT COUNT(*) FROM plays")
    for target in ("opponent", ""):
        assert _post(client, f"/playbook/play/{src}/copy-to-team", data={"target_team": target}).status_code == 302
    assert _count(db, "SELECT COUNT(*) FROM plays") == before


def test_duplicate_keeps_saved_choreography(client, db, choreo_base):
    pid = _save_play(client, name="Sticky", steps_json=STEPS_3[:1])
    doc = {"source": "user_save", "steps": [{"step_index": 0, "positions": {"o1": {"x": 1, "y": 2}},
           "movements": [{"from": "o1", "to": "o2", "type": "pass"}], "coachOrder": True}]}
    assert client.put(f"/api/playbook/choreography/{pid}", json=doc).status_code == 200
    dup = int(re.search(r"/play/(\d+)/edit", _post(client, f"/playbook/play/{pid}/duplicate").headers["Location"]).group(1))
    got = client.get(f"/api/playbook/choreography/{dup}").get_json()
    assert got["sticky"] is True
    assert got["choreography"]["steps"][0]["movements"] == [
        {"from": "o1", "to": "o2", "type": "pass", "timing": "sync"}]
    assert got["choreography"]["play_id"] == dup and got["choreography"]["steps"][0]["coachOrder"] is True

    # Copy to another team carries it too.
    r = _post(client, f"/playbook/play/{pid}/copy-to-team", data={"target_team": "hs_girls"})
    copied = int(re.search(r"copied=(\d+)", r.headers["Location"]).group(1))
    got = client.get(f"/api/playbook/choreography/{copied}").get_json()
    assert got["sticky"] is True and got["choreography"]["play_id"] == copied
    assert got["choreography"]["steps"][0]["positions"] == {"o1": {"x": 1.0, "y": 2.0}}

    # The copies are independent: clearing the copy's choreography keeps the original's.
    client.delete(f"/api/playbook/choreography/{dup}")
    assert client.get(f"/api/playbook/choreography/{pid}").get_json()["sticky"] is True


# ── 4. share links and view/edit/share modes ─────────────────────────────────


def test_share_link_and_mode_controls(client, db):
    pid = _save_play(client, name="Shared Horns", description="public desc", steps_json=STEPS_3)
    secret = _save_play(client, name="Secret Zone Sauce", steps_json=STEPS_3[:1])

    r1 = client.post(f"/api/playbook/play/{pid}/share").get_json()
    r2 = client.post(f"/api/playbook/play/{pid}/share").get_json()
    assert r1["token"] == r2["token"] and r1["url"].endswith(f"/play/share/{r1['token']}")
    assert db.execute("SELECT share_token FROM plays WHERE id=?", (secret,)).fetchone()[0] is None
    assert client.post("/api/playbook/play/999999/share").status_code == 404

    share = client.get(f"/play/share/{r1['token']}")
    assert share.status_code == 200
    html = share.get_data(as_text=True)
    assert "Shared Horns" in html and "public desc" in html
    assert 'const viewMode = "share"' in html and "const isReadOnly = true" in html
    assert "Shared play — view and animate only" in html
    assert 'id="playForm"' not in html
    assert 'onclick="addStep()"' not in html
    assert f'/playbook/play/{pid}/edit"' not in html
    assert "Secret Zone Sauce" not in html
    assert f"/playbook/play/{secret}" not in html
    m = re.search(r"const editingSteps = (\[.*?\]);\n", html)
    assert [s["label"] for s in json.loads(m.group(1))] == ["Initial", "Flare", "Finish"]

    assert client.get("/play/share/not-a-real-token").status_code == 404
    assert client.get(f"/play/share/{r1['token']}x").status_code == 404

    view = client.get(f"/playbook/play/{pid}").get_data(as_text=True)
    assert 'const viewMode = "view"' in view and "const isReadOnly = true" in view
    assert 'id="playForm"' not in view
    assert f'href="/playbook/play/{pid}/edit"' in view
    assert "<strong>not saved</strong> in View" in view
    assert 'onclick="addStep()"' in view  # View may fix sheets for Play All
    assert r1["url"] in view  # share URL pre-filled for Copy Share Link

    edit = client.get(f"/playbook/play/{pid}/edit").get_data(as_text=True)
    assert 'const viewMode = "editor"' in edit and "const isReadOnly = false" in edit
    assert 'id="playForm"' in edit
    assert f'name="play_id" value="{pid}"' in edit

    # Deleting the play kills the link.
    _post(client, f"/playbook/play/{pid}/delete")
    assert client.get(f"/play/share/{r1['token']}").status_code == 404


def test_share_link_can_be_revoked(client, db):
    pid = _save_play(client, name="Revoke me")
    token = client.post(f"/api/playbook/play/{pid}/share").get_json()["token"]
    view = client.get(f"/playbook/play/{pid}").get_data(as_text=True)
    assert 'id="revokeShareBtn"' in view and "revokePlayShareLink()" in view
    r = client.delete(f"/api/playbook/play/{pid}/share")
    assert r.status_code == 200 and r.get_json() == {"ok": True, "revoked": True}
    assert client.get(f"/play/share/{token}").status_code == 404
    assert client.get(f"/playbook/play/{pid}").status_code == 200
    assert db.execute("SELECT share_token FROM plays WHERE id=?", (pid,)).fetchone()[0] is None
    assert client.delete(f"/api/playbook/play/{pid}/share").get_json()["revoked"] is False
    assert client.delete("/api/playbook/play/999999/share").status_code == 404
    # Sharing again mints a fresh token; the revoked one stays dead.
    new_token = client.post(f"/api/playbook/play/{pid}/share").get_json()["token"]
    assert new_token != token
    assert client.get(f"/play/share/{new_token}").status_code == 200
    assert client.get(f"/play/share/{token}").status_code == 404
    # The public share page never offers the revoke control.
    assert 'id="revokeShareBtn"' not in client.get(f"/play/share/{new_token}").get_data(as_text=True)


def test_share_page_assets_reachable_when_sign_in_required(client, db, app, choreo_base):
    upl = Path(app.config["UPLOAD_FOLDER"]) / "play_imports"
    upl.mkdir(parents=True, exist_ok=True)
    (upl / "sheet.png").write_bytes(td.png_bytes())
    pid = _save_play(client, name="Sheet play", steps_json=[
        {"label": "s1", "positions": {}, "source_image": "/uploads/play_imports/sheet.png"}])
    client.put(f"/api/playbook/choreography/{pid}", json={"steps": [{"positions": {"o1": {"x": 1, "y": 1}}}]})
    token = client.post(f"/api/playbook/play/{pid}/share").get_json()["token"]
    db.execute("""INSERT INTO app_settings (key, value) VALUES ('feature.ENABLE_AUTH_MIDDLEWARE', '1')
                  ON CONFLICT(key) DO UPDATE SET value=excluded.value""")
    db.commit()
    anon = app.test_client()
    page = anon.get(f"/play/share/{token}")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    # The share page loads its sheets + choreography through token-scoped routes ...
    assert f'const shareAssetBase = "/play/share/{token}"' in html
    img = anon.get(f"/play/share/{token}/uploads/play_imports/sheet.png")
    assert img.status_code == 200 and img.data == td.png_bytes()
    ch = anon.get(f"/play/share/{token}/choreography")
    assert ch.status_code == 200 and ch.get_json()["sticky"] is True
    assert ch.get_json()["choreography"]["steps"][0]["positions"] == {"o1": {"x": 1.0, "y": 1.0}}
    # ... which expose only this play's assets: not the rest of /uploads, not other plays.
    (upl / "private.png").write_bytes(td.png_bytes())
    assert anon.get(f"/play/share/{token}/uploads/play_imports/private.png").status_code == 404
    assert anon.get(f"/play/share/{token}/uploads/../app.db").status_code == 404
    assert anon.get("/uploads/play_imports/sheet.png").status_code == 302  # global /uploads stays gated
    assert anon.get(f"/api/playbook/choreography/{pid}").status_code == 401
    assert anon.post(f"/play/share/{token}/sheet-extract",
                     json={"image_url": "/uploads/play_imports/private.png"}).status_code == 404
    assert anon.get("/play/share/bogus/uploads/play_imports/sheet.png").status_code == 404
    assert anon.get("/play/share/bogus/choreography").status_code == 404
    # Revoking the link revokes its assets too (the test client is not signed in, so
    # revoke with the gate off, then turn it back on).
    db.execute("UPDATE app_settings SET value='0' WHERE key='feature.ENABLE_AUTH_MIDDLEWARE'")
    db.commit()
    assert client.delete(f"/api/playbook/play/{pid}/share").get_json()["revoked"] is True
    db.execute("UPDATE app_settings SET value='1' WHERE key='feature.ENABLE_AUTH_MIDDLEWARE'")
    db.commit()
    assert anon.get(f"/play/share/{token}/uploads/play_imports/sheet.png").status_code == 404
    assert anon.get(f"/play/share/{token}/choreography").status_code == 404


# ── 5. import, choreography, play-match ──────────────────────────────────────


def test_pdf_import_parse_and_save(client, db, app):
    upload_root = Path(app.config["UPLOAD_FOLDER"])
    # two-page PDF → one preview page + bulk recommendation
    r = client.post("/playbook/import/parse", data={"file": (io.BytesIO(td.playbook_pdf_bytes()), "Plays.PDF")},
                    content_type="multipart/form-data")
    assert r.status_code == 200, r.data
    body = r.get_json()
    assert (body["is_pdf"], body["page_count"], body["recommend_bulk_import"]) == (True, 2, True)
    assert len(body["extracted_images"]) == 1 and body["extracted_images"][0]["page"] == 1
    assert body["file_url"] == body["extracted_images"][0]["url"]
    assert set(body["suggested_positions"]) == {"1", "2", "3", "4", "5"}
    img = client.get(body["file_url"])
    assert img.status_code == 200 and img.data[:8] == b"\x89PNG\r\n\x1a\n"
    assert all(Path(p).resolve().is_relative_to(upload_root.resolve())
               for p in [body["file_path"]] + [e["file_path"] for e in body["extracted_images"]])

    one = td.pdf_bytes([["ONE PAGE"]], draw_shapes=True)
    b1 = client.post("/playbook/import/parse", data={"file": (io.BytesIO(one), "one.pdf")},
                     content_type="multipart/form-data").get_json()
    assert (b1["page_count"], b1["recommend_bulk_import"], len(b1["extracted_images"])) == (1, False, 1)

    # odd inputs
    bad = client.post("/playbook/import/parse", data={"file": (io.BytesIO(b"%PDF-1.4 garbage"), "bad.pdf")},
                      content_type="multipart/form-data")
    assert bad.status_code == 400 and "Could not read PDF" in bad.get_json()["error"]
    empty = td.pdf_bytes([[]])
    e = client.post("/playbook/import/parse", data={"file": (io.BytesIO(empty), "blank.pdf")},
                    content_type="multipart/form-data")
    assert e.status_code == 200 and e.get_json()["page_count"] == 1
    png = client.post("/playbook/import/parse", data={"file": (io.BytesIO(td.png_bytes()), "diagram.png")},
                      content_type="multipart/form-data").get_json()
    assert png["is_pdf"] is False and png["file_url"].endswith(".png")
    assert client.post("/playbook/import/parse", data={}, content_type="multipart/form-data").status_code == 400
    # filename is never used for the stored path
    trav = client.post("/playbook/import/parse",
                       data={"file": (io.BytesIO(td.png_bytes()), "../../../evil.png")},
                       content_type="multipart/form-data").get_json()
    assert Path(trav["file_path"]).parent.resolve() == (upload_root / "play_imports").resolve()

    # save the imported play into the session team
    client.get("/playbook?team=jh_boys")
    zone = _cat(client, "defense/zone")
    r = client.post("/playbook/import/save", json={
        "name": "Imported Zone", "description": "from pdf", "category_id": str(zone["id"]),
        "playbook_id": "", "tags": "import", "diagram_json": "{}",
        "steps_json": json.dumps([{"label": "p1", "positions": {"o1": {"x": 1, "y": 2}}},
                                  {"label": "p2", "positions": {}, "source_image": "/uploads/x/p2.png"}]),
        "source_image": body["file_url"],
    })
    assert r.status_code == 200
    new_id = r.get_json()["id"]
    assert r.get_json()["redirect"] == f"/playbook/play/{new_id}/edit"
    play = _api_play(client, new_id)["play"]
    assert (play["team_key"], play["category_id"], play["category"]) == ("jh_boys", zone["id"], "defense")
    steps = _steps(client, new_id)
    assert [(s["step_number"], s["label"], s["source_image"]) for s in steps] == [
        (0, "p1", body["file_url"]), (1, "p2", "/uploads/x/p2.png")]
    assert client.post("/playbook/import/save", json={"name": ""}).status_code == 400


def test_import_parse_rejects_active_content(client, db, app):
    r = client.post("/playbook/import/parse",
                    data={"file": (io.BytesIO(b"<script>alert(document.cookie)</script>"), "diagram.html")},
                    content_type="multipart/form-data")
    served = client.get(r.get_json()["file_url"]) if r.status_code == 200 else None
    assert r.status_code == 400
    assert served is None or "text/html" not in served.headers.get("Content-Type", "")
    assert "Unsupported file type" in r.get_json()["error"]
    for name in ("x.svg", "x.js", "x.htm", "noext"):
        rr = client.post("/playbook/import/parse", data={"file": (io.BytesIO(b"<svg onload=alert(1)>"), name)},
                         content_type="multipart/form-data")
        assert rr.status_code == 400, name
    # Nothing refused was written under /uploads.
    imports = Path(app.config["UPLOAD_FOLDER"]) / "play_imports"
    assert not imports.exists() or not any(imports.iterdir())
    # Allowed image types still import (extension check is case-insensitive).
    ok = client.post("/playbook/import/parse", data={"file": (io.BytesIO(td.png_bytes()), "Diagram.JPEG")},
                     content_type="multipart/form-data")
    assert ok.status_code == 200 and ok.get_json()["file_url"].endswith(".jpeg")


def _bulk_pdf(names):
    return td.pdf_bytes([["21-22 - Liberty Charter Patriots - Offense - Plays", "Plays", n] for n in names])


def test_bulk_import_parse_and_save(client, db):
    r = client.post("/api/playbook/bulk/parse", data={"file": (io.BytesIO(_bulk_pdf(["Horns", "Zipper"])), "b.pdf")},
                    content_type="multipart/form-data")
    assert r.status_code == 200, r.data
    body = r.get_json()
    assert [p["play_name"] for p in body["plays"]] == ["Horns", "Zipper"]
    assert body["total_plays"] == 2 and body["sections"] == {"Offense": {"count": 2, "pages": 2}}
    man = _cat(client, "offense/man")
    assert {p["category_id"] for p in body["plays"]} == {man["id"]}
    r = client.post("/api/playbook/bulk/save", json={"plays": [
        {"play_name": p["play_name"], "section": p["section"], "category_id": p["category_id"],
         "pages": p["pages"]} for p in body["plays"]]})
    assert r.status_code == 200 and r.get_json()["saved_count"] == 2
    for saved, parsed in zip(r.get_json()["saved"], body["plays"]):
        steps = _steps(client, saved["id"])
        assert [s["source_image"] for s in steps] == [pg["image_url"] for pg in parsed["pages"]]


def test_bulk_import_does_not_overwrite_earlier_sheets(client, db, app):
    a = client.post("/api/playbook/bulk/parse", data={"file": (io.BytesIO(_bulk_pdf(["Horns"])), "a.pdf")},
                    content_type="multipart/form-data").get_json()
    url_a = a["plays"][0]["pages"][0]["image_url"]
    bytes_a = client.get(url_a).data
    client.post("/api/playbook/bulk/save", json={"plays": [
        {"play_name": "Horns", "section": "Offense", "pages": a["plays"][0]["pages"]}]})
    b = client.post("/api/playbook/bulk/parse",
                    data={"file": (io.BytesIO(td.pdf_bytes([["21-22 - Liberty Charter Patriots - Defense - Plays", "Plays", "Totally different", "x" * 50]], draw_shapes=True)), "b.pdf")},
                    content_type="multipart/form-data").get_json()
    url_b = b["plays"][0]["pages"][0]["image_url"]
    assert url_a != url_b
    assert client.get(url_a).data == bytes_a


def test_bulk_import_saves_into_active_team(client, db):
    client.get("/playbook?team=hs_girls")
    r = client.post("/api/playbook/bulk/save", json={"plays": [{"play_name": "Girls Set", "section": "Offense", "pages": []}]})
    pid = r.get_json()["saved"][0]["id"]
    assert db.execute("SELECT team_key FROM plays WHERE id=?", (pid,)).fetchone()[0] == "hs_girls"
    assert "Girls Set" in client.get("/playbook?team=hs_girls").get_data(as_text=True)
    assert "Girls Set" not in client.get("/playbook?team=hs_boys").get_data(as_text=True)
    # An explicit team_key in the body wins over the session team.
    r = client.post("/api/playbook/bulk/save", json={"team_key": "jh_boys", "plays": [
        {"play_name": "JH Set", "section": "Offense", "pages": []}]})
    pid = r.get_json()["saved"][0]["id"]
    assert db.execute("SELECT team_key FROM plays WHERE id=?", (pid,)).fetchone()[0] == "jh_boys"


def test_bulk_sheet_url_resolves_to_its_vector_pdf(client, db, app, tmp_path):
    from playbook_vector_extract import resolve_pdf_page_from_sheet

    app.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    body = client.post("/api/playbook/bulk/parse",
                       data={"file": (io.BytesIO(_bulk_pdf(["Horns", "Zipper"])), "b.pdf")},
                       content_type="multipart/form-data").get_json()
    url = body["plays"][1]["pages"][0]["image_url"]
    resolved = resolve_pdf_page_from_sheet(url, app_root=tmp_path)
    assert resolved is not None
    pdf, page = resolved
    assert page == 2 and pdf.parent.resolve() == (tmp_path / "uploads" / "bulk_imports").resolve()
    assert pdf.is_file() and pdf.read_bytes()[:5] == b"%PDF-"
    # Same answer when the upload folder is configured away from the app root (as the routes pass it).
    assert resolve_pdf_page_from_sheet(url, app_root=ROOT, upload_folder=tmp_path / "uploads") == (pdf, 2)


def test_sheet_extract_refuses_pdfs_outside_uploads(client, db, app, tmp_path):
    """Absolute / traversal sheet paths must never reach a PDF or image outside UPLOAD_FOLDER + app root."""
    import os

    from playbook_sheet_align import resolve_upload_path
    from playbook_vector_extract import resolve_pdf_page_from_sheet

    outside = tmp_path / "outside"
    (outside / "secret").mkdir(parents=True)
    (outside / "secret.pdf").write_bytes(td.pdf_bytes([["1", "2", "3", "4", "5"]], draw_shapes=True))
    png = outside / "secret" / "page_0001.png"
    png.write_bytes(td.png_bytes())
    upload_root = Path(app.config["UPLOAD_FOLDER"]).resolve()
    assert not png.resolve().is_relative_to(upload_root) and not png.resolve().is_relative_to(ROOT)

    traversal = "/uploads/" + os.path.relpath(png, upload_root).replace(os.sep, "/")
    assert ".." in traversal
    for bad in (str(png), traversal):
        assert resolve_pdf_page_from_sheet(bad, app_root=ROOT, upload_folder=upload_root) is None, bad
        with pytest.raises(FileNotFoundError):
            resolve_upload_path(bad, ROOT, upload_root)
        for route in ("/api/playbook/sheet-extract", "/api/playbook/sheet-align"):
            r = client.post(route, json={"image_url": bad})
            assert r.status_code == 404, (route, bad, r.data[:200])
            assert "outside uploads" in r.get_json()["error"]
        r = client.post("/api/playbook/sheet-paths", json={
            "image_url": bad, "from_positions": {"o1": {"x": 1, "y": 1}}, "to_positions": {"o1": {"x": 2, "y": 2}}})
        assert r.status_code == 404, (bad, r.data[:200])

    # A legit upload still resolves.
    (upload_root / "play_imports").mkdir(exist_ok=True)
    (upload_root / "play_imports" / "ok.png").write_bytes(td.png_bytes())
    assert resolve_upload_path("/uploads/play_imports/ok.png", ROOT, upload_root) == upload_root / "play_imports" / "ok.png"


def test_choreography_round_trip(client, db, choreo_base):
    pid = _save_play(client, name="Choreo", steps_json=STEPS_3[:2])
    other = _save_play(client, name="Other")
    assert client.get(f"/api/playbook/choreography/{pid}").get_json() == {
        "ok": True, "sticky": False, "choreography": None}
    doc = {"source": "user_save", "steps": [
        {"step_index": 0, "source_image": "/uploads/a.png", "court_frac": {"x": 0.1},
         "positions": {"o1": {"x": 10.123, "y": 20}, "d1": {"x": 1, "y": 1}, "o2": {"x": "bad"}},
         "movements": [{"from": "o2", "to": "o3", "type": "SCREEN", "timing": "optional"},
                       {"from": "o1", "to": "o2", "type": "pass"},
                       {"from": "o4", "type": "teleport"}],
         "coachOrder": True,
         "ink": {"paths": {"o1": [{"x": 1, "y": 1}, {"x": 2, "y": 2}], "o2": [{"x": 1, "y": 1}]},
                 "marks": {"o1": "cut"}, "passes": []}},
        "junk",
        {"positions": {"o5": {"x": 5, "y": 6}}},
    ]}
    r = client.put(f"/api/playbook/choreography/{pid}", json=doc)
    assert r.status_code == 200
    saved = r.get_json()["choreography"]
    assert (saved["play_id"], saved["source"], saved["sticky"], saved["version"]) == (pid, "user_save", True, 1)
    assert saved["steps"] == [
        {"step_index": 0, "source_image": "/uploads/a.png", "court_frac": {"x": 0.1},
         "positions": {"o1": {"x": 10.12, "y": 20.0}},
         "ink": {"paths": {"o1": [{"x": 1.0, "y": 1.0}, {"x": 2.0, "y": 2.0}]}, "marks": {"o1": "cut"}, "passes": []},
         "movements": [{"from": "o2", "to": "o3", "type": "screen", "timing": "optional"},
                       {"from": "o1", "to": "o2", "type": "pass", "timing": "sync"}],
         "coachOrder": True},
        {"step_index": 2, "source_image": "", "court_frac": None, "positions": {"o5": {"x": 5.0, "y": 6.0}}},
    ]
    assert client.get(f"/api/playbook/choreography/{pid}").get_json()["choreography"] == saved
    assert (choreo_base / "choreography" / f"{pid}.json").is_file()
    assert client.get(f"/api/playbook/choreography/{other}").get_json()["sticky"] is False

    # POST also saves; empty/invalid is refused and leaves the saved doc alone.
    assert client.post(f"/api/playbook/choreography/{pid}", json={"steps": []}).status_code == 400
    assert client.put(f"/api/playbook/choreography/{pid}", json={"steps": ["x"]}).status_code == 400
    assert client.get(f"/api/playbook/choreography/{pid}").get_json()["choreography"] == saved
    assert client.put("/api/playbook/choreography/999999", json=doc).status_code == 404

    assert client.delete(f"/api/playbook/choreography/{pid}").get_json() == {"ok": True, "deleted": True, "sticky": False}
    assert client.delete(f"/api/playbook/choreography/{pid}").get_json()["deleted"] is False
    assert client.get(f"/api/playbook/choreography/{pid}").get_json()["sticky"] is False


def test_reordered_sheet_keeps_its_choreography_when_saved():
    src = (ROOT / "templates/playbook.html").read_text(encoding="utf-8")
    script = "\n".join([
        _js_function(src, "moveStep"),
        _js_function(src, "buildChoreographyPayload"),
        """
function canFixAnimation() { return true; }
function saveCurrentStepNotes() {} function markStepsDirty() {} function markAnimationOrderDirty() {}
function renderStep() {} function updateStepList() {} function updateMovementList() {}
var currentStep = 0;
var steps = [{source_image: '/A.png', movements: []}, {source_image: '/B.png', movements: []}];
var sheetAlignByStep = [{court_frac: null, positions: {o1: {x: 1, y: 1}}},
                        {court_frac: null, positions: {o1: {x: 2, y: 2}}}];
var sheetSessionInkByStep = [{paths: {o1: 'A'}}, {paths: {o1: 'B'}}];
var sheetStickyInkByStep = [null, null];
moveStep(0, 1);
const p = buildChoreographyPayload('user_save');
console.log(JSON.stringify(p.steps.map(s => [s.source_image, s.positions.o1.x, s.ink.paths.o1])));
"""])
    assert _run_node(script) == [["/B.png", 2, "B"], ["/A.png", 1, "A"]]

    # Three sheets, last dragged to the front; sticky ink only known for the first sheet.
    script3 = "\n".join([
        _js_function(src, "moveStep"),
        """
function canFixAnimation() { return true; }
function saveCurrentStepNotes() {} function markStepsDirty() {}
function renderStep() {} function updateStepList() {} function updateMovementList() {}
var currentStep = 2;
var steps = ['A', 'B', 'C'];
var sheetAlignByStep = ['a', 'b', 'c'];
var sheetSessionInkByStep = ['ia', 'ib', 'ic'];
var sheetStickyInkByStep = ['sa'];
moveStep(2, 0);
console.log(JSON.stringify([steps, sheetAlignByStep, sheetSessionInkByStep, sheetStickyInkByStep, currentStep]));
"""])
    assert _run_node(script3) == [["C", "A", "B"], ["c", "a", "b"], ["ic", "ia", "ib"], [None, "sa", None], 0]


def _seed_game(db, game_key, samples, events):
    for ts, x, y, tid in samples:
        db.execute(
            """INSERT INTO detections (game_id, frame_number, timestamp_ms, object_class, confidence,
                                       x_center, y_center, width, height, tracker_id)
               VALUES (?, ?, ?, 'person', 0.9, ?, ?, 40, 80, ?)""",
            (game_key, int(ts / 33), ts, x, y, tid))
    for ts, et in events:
        db.execute("""INSERT INTO events (game_id, event_type, timestamp_ms, source_type, confidence, review_status)
                      VALUES (?, ?, ?, 'ai', 0.5, 'pending')""", (game_key, et, ts))
    db.commit()


RIP = {"o1": (250, 320), "o2": (400, 220), "o3": (100, 220), "o4": (180, 100), "o5": (320, 100)}
TRI = {"o1": (250, 280), "o2": (120, 160), "o3": (380, 160), "o4": (200, 80), "o5": (300, 80)}


def test_play_match_for_game(client, db, choreo_base, tmp_path):
    rip = _save_play(client, name="Rip")
    tri = _save_play(client, name="Triangle")
    _save_play(client, name="Empty")  # no choreography / steps → not in library
    for pid, pos in ((rip, RIP), (tri, TRI)):
        client.put(f"/api/playbook/choreography/{pid}", json={"steps": [
            {"positions": {k: {"x": x, "y": y} for k, (x, y) in pos.items()}}]})

    def samples(pos, t0):
        return [(t0 + dt, x, y + dy, int(k[1])) for dt, dy in ((0, 0), (3000, -10)) for k, (x, y) in pos.items()]

    _seed_game(db, "gm-rip", samples(RIP, 0) + samples(TRI, 10000),
               [(0, "possession_change"), (5000, "made_two"), (10000, "possession_change"), (15000, "turnover")])
    _seed_game(db, "gm-other", samples(TRI, 0), [(0, "possession_change"), (6000, "made_two")])

    r = client.post("/api/film/gm-rip/play-matches/run", json={"top_k": 2})
    assert r.status_code == 200, r.data
    res = r.get_json()
    assert (res["game_id"], res["library_size"], res["auto_accept"], res["cached"]) == ("gm-rip", 2, False, False)
    wins = [(p["start_ms"], p["end_ms"], p["window_source"]) for p in res["possessions"]]
    assert wins == [(0, 5000, "event_boundaries"), (5000, 10000, "event_boundaries"), (10000, 15000, "event_boundaries")]
    assert res["possessions"][0]["top_play_name"] == "Rip"
    assert res["possessions"][2]["top_play_name"] == "Triangle"
    assert all(len(p["suggestions"]) <= 2 for p in res["possessions"])
    assert [s["rank"] for s in res["possessions"][0]["suggestions"]] == list(range(1, len(res["possessions"][0]["suggestions"]) + 1))
    assert {s["play_id"] for p in res["possessions"] for s in p["suggestions"]} <= {rip, tri}

    cached = client.get("/api/film/gm-rip/play-matches").get_json()
    assert cached["cached"] is True and cached["possessions"] == res["possessions"]

    other = client.get("/api/film/gm-other/play-matches").get_json()
    assert (other["game_id"], other["cached"]) == ("gm-other", False)
    assert [p["top_play_name"] for p in other["possessions"]] == ["Triangle"]
    # first game's cached results untouched
    assert client.get("/api/film/gm-rip/play-matches").get_json()["possessions"] == res["possessions"]
    stored = sorted(p.name for p in (tmp_path / "play_matches").iterdir())
    assert stored == ["gm-other.json", "gm-rip.json"]


def test_play_match_cache_is_per_game(client, db, choreo_base):
    rip = _save_play(client, name="Rip")
    client.put(f"/api/playbook/choreography/{rip}", json={"steps": [
        {"positions": {k: {"x": x, "y": y} for k, (x, y) in RIP.items()}}]})
    _seed_game(db, "jh_adrian,_or_A", [(dt, x, y, int(k[1])) for dt in (0, 3000) for k, (x, y) in RIP.items()],
               [(0, "possession_change"), (5000, "made_two")])
    assert client.post("/api/film/jh_adrian,_or_A/play-matches/run", json={}).get_json()["possessions"]
    other = client.get("/api/film/jh_adrian__or_A/play-matches").get_json()
    assert other["game_id"] == "jh_adrian__or_A"
    assert other["possessions"] == []
    assert other["cached"] is False
    # The punctuated game still reads back its own cached result.
    own = client.get("/api/film/jh_adrian,_or_A/play-matches").get_json()
    assert (own["game_id"], own["cached"]) == ("jh_adrian,_or_A", True)
    assert own["possessions"][0]["top_play_name"] == "Rip"


# ── 6. opponent playbooks ────────────────────────────────────────────────────


def test_opponent_playbooks_create_list_view(client, db):
    assert client.get("/playbook/opponents").status_code == 200
    r = _post(client, "/playbook/opponents", data={"name": "Borah Lions", "description": "zone heavy"})
    assert r.status_code == 302
    opp_id = int(re.search(r"/playbook/opponents/(\d+)$", r.headers["Location"]).group(1))
    row = db.execute("SELECT name, kind, opponent_name, description FROM playbooks WHERE id=?", (opp_id,)).fetchone()
    assert tuple(row) == ("Borah Lions", "opponent", "Borah Lions", "zone heavy")

    r = _post(client, "/playbook/opponents", data={"name": "  "})
    assert r.status_code == 302 and r.headers["Location"].endswith("/playbook/opponents")
    assert _count(db, "SELECT COUNT(*) FROM playbooks WHERE kind='opponent'") == 1

    create = client.get(f"/playbook/create?playbook_id={opp_id}").get_data(as_text=True)
    assert f'<option value="{opp_id}" selected>Borah Lions</option>' in create

    pid = _save_play(client, name="Borah 1-3-1", playbook_id=str(opp_id), steps_json=STEPS_3[:2])
    _save_play(client, name="Our Horns", steps_json=STEPS_3[:1])

    listing = client.get("/playbook/opponents").get_data(as_text=True)
    assert "Borah Lions" in listing
    detail = client.get(f"/playbook/opponents/{opp_id}").get_data(as_text=True)
    assert "Borah 1-3-1" in detail and "2 steps" in detail and "zone heavy" in detail
    assert "Our Horns" not in detail
    ours = client.get("/playbook?team=hs_boys").get_data(as_text=True)
    assert "Our Horns" in ours and "Borah 1-3-1" not in ours
    assert _api_play(client, pid)["play"]["playbook_id"] == opp_id

    # a team playbook id / unknown id is not an opponent page
    team_pb = db.execute("INSERT INTO playbooks (name) VALUES ('Program')").lastrowid
    db.commit()
    for bad in (team_pb, 999999):
        r = client.get(f"/playbook/opponents/{bad}")
        assert r.status_code == 302 and r.headers["Location"].endswith("/playbook/opponents")
    # tree's Opponents node counts opponent playbooks
    tree = client.get("/api/playbook/categories").get_json()["tree"]
    opp_node = next(n for n in tree if n["slug_path"] == "opponents")
    assert opp_node["play_count"] == 1
