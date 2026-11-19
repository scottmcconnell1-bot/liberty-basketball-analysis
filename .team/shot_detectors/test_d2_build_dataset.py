"""Tests for d2_build_dataset.py (spec 23 section 7). No GPU, no video."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import d2_build_dataset as b  # noqa: E402

F0, F1 = b.FILMS[0], b.FILMS[2]


def nm(film, fn):
    return "%s_fr%06d.jpg" % (film, fn)


def test_box_conversion_standard_and_edge_crop():
    assert b.to_yolo([250, 210, 20, 20], 520, 440) == "0 0.500000 0.500000 0.038462 0.045455"
    assert b.to_yolo([0, 369, 26, 20], 520, 389) == "0 0.025000 0.974293 0.050000 0.051414"
    with pytest.raises(ValueError):
        b.to_yolo([510, 380, 20, 20], 520, 389)       # runs past the edge crop


def test_refuses_film_not_in_the_7():
    with pytest.raises(ValueError):
        b.parse_name("LIBERTY_H_v_NOTUS_A1_20260809_221334_fr000100.jpg")
    with pytest.raises(ValueError):
        b.parse_name("LIBERTY_A_v_ADRIAN_H_20260809_221334_fr000100.jpg")
    assert b.parse_name(nm(F0, 95)) == (F0, 95)


def test_windows_break_on_gap_over_40():
    w = b.windows([nm(F0, 100), nm(F0, 140), nm(F0, 181), nm(F1, 120)])
    assert w[nm(F0, 100)] == w[nm(F0, 140)] != w[nm(F0, 181)]
    assert w[nm(F1, 120)].startswith(F1)


def many():
    names = []
    for film in b.FILMS:
        for k in range(20):
            names += [nm(film, 1000 * k + j) for j in (0, 5, 12)]
    return names


def test_split_never_shares_a_window_and_is_reproducible():
    win = b.windows(many())
    sp = b.split(win)
    by_win = {}
    for n, w in win.items():
        by_win.setdefault(w, set()).add(sp[n])
    assert all(len(s) == 1 for s in by_win.values())
    for film in b.FILMS:
        vals = {w for n, w in win.items() if w.startswith(film) and sp[n] == "val"}
        assert len(vals) == 3                       # round(0.15 * 20)
    assert b.split(b.windows(list(reversed(many())))) == sp


def fake_set(tmp_path):
    frames = tmp_path / "frames"
    frames.mkdir()
    rows = []
    for i, n in enumerate(many()):
        (frames / n).write_bytes(b"jpg")
        rows.append({"frame": n, "boxes": [[10, 10, 20, 20]] if i % 3 else [], "class": "basketball"})
    lab = tmp_path / "labels_live.json"
    lab.write_text(json.dumps(rows))
    return lab, frames, rows


def test_build_writes_empty_label_for_no_ball_and_same_split_twice(tmp_path):
    lab, frames, rows = fake_set(tmp_path)
    size = lambda p: (520, 440)  # noqa: E731
    c = b.build(str(lab), str(frames), str(tmp_path / "ds1"), size_of=size)
    b.build(str(lab), str(frames), str(tmp_path / "ds2"), size_of=size)
    s1 = json.load(open(tmp_path / "ds1" / "split.json"))
    s2 = json.load(open(tmp_path / "ds2" / "split.json"))
    assert s1["frames"] == s2["frames"]
    no_ball = rows[0]["frame"]
    part = s1["frames"][no_ball]["split"]
    assert (tmp_path / "ds1" / "labels" / part / (no_ball[:-4] + ".txt")).read_text() == ""
    assert sum(sum(v) for v in c.values()) == len(rows)
    assert "names:\n  0: basketball" in (tmp_path / "ds1" / "data.yaml").read_text()


def test_refuses_non_empty_output(tmp_path):
    lab, frames, _ = fake_set(tmp_path)
    out = tmp_path / "ds"
    out.mkdir()
    (out / "x").write_text("x")
    with pytest.raises(SystemExit):
        b.build(str(lab), str(frames), str(out), size_of=lambda p: (520, 440))


# --- d2_train.py helpers (no GPU, no video) -----------------------------------------------
def test_extract_gate_rule(tmp_path):
    import d2_train as t
    cand = tmp_path / "candidates.json"
    assert t.extract_ok(0, "", str(cand))
    assert not t.extract_ok(1, "MAPPING CHECK GATE FAILED: ...", str(cand))   # no candidates written
    cand.write_text("{}")
    assert t.extract_ok(1, "MAPPING CHECK GATE FAILED: ...", str(cand))
    assert not t.extract_ok(1, "Traceback ... CUDA error", str(cand))         # any other error stops


def test_train_numbers_fixed_by_spec():
    import d2_train as t
    a = t.TRAIN_ARGS
    assert (a["imgsz"], a["batch"], a["freeze"], a["epochs"], a["patience"], a["seed"], a["workers"]) == (640, 16, 10, 30, 10, 42, 2)
    assert a["single_cls"] and a["deterministic"] and a["exist_ok"] is False
    assert "models/" not in t.NEW and t.NEW.startswith("C:/Users/scott/Documents/Liberty_Shot_Outputs/")
