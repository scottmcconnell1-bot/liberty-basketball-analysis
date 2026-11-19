"""Tests for D1 keep_ball_detections — arc + rule only (no torch).

Handmade candidates.json in a temp dir. Never writes under the repo outputs path
for real films; never reads track['result'] inside arc/rule functions.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import keep_ball_detections as kbd  # noqa: E402
from small_fixes_v6_copy import fall_through_check, decide_shot  # noqa: E402


def _track_base(*, ball, bodd, hoop, result="make"):
    return {
        "t": 1000,
        "result": result,
        "hoop": hoop,
        "ball": ball,
        "bodd": bodd,
    }


def test_constants_match_spec():
    assert kbd.ZONE_HOOP_WIDTHS_H == 3.0
    assert kbd.ZONE_ABOVE_HOOP_WIDTHS == 4.0
    assert kbd.ZONE_BELOW_PX == 300
    assert kbd.CANDIDATE_CAP == 3
    assert kbd.MIN_POINTS_BEFORE == 4
    assert kbd.MIN_POINTS_AFTER == 3
    assert kbd.RANSAC_ITERATIONS == 100
    assert kbd.RANSAC_SEED == 42
    assert kbd.RESIDUAL_HOOP_W_FRAC == 0.15
    assert kbd.WINDOW_BEFORE_START == -15
    assert kbd.WINDOW_BEFORE_END == 0
    assert kbd.WINDOW_AFTER_START == 1
    assert kbd.WINDOW_AFTER_END == 12
    assert kbd.MAPPING_MIN_MATCH_RATE == 0.90
    assert kbd.BALL_CONFIDENCE == 0.28
    assert kbd.MAPPING_MATCH_PX == 3
    assert (kbd.CROP_LEFT_RIGHT, kbd.CROP_ABOVE, kbd.CROP_BELOW, kbd.PREDICT_IMGSZ) == (260, 200, 240, 640)


class _FakeBox:
    def __init__(self, xyxy, conf=0.9, cls=0):
        self.xyxy = [xyxy]
        self.conf = [conf]
        self.cls = [cls]


class _FakeModel:
    """Records the crop and settings it was given; returns boxes in crop coordinates."""

    names = {0: "basketball"}

    def __init__(self, boxes):
        self.boxes = boxes
        self.calls = []

    def predict(self, crop, conf, imgsz, verbose):
        self.calls.append({"shape": crop.shape, "conf": conf, "imgsz": imgsz})
        return [type("P", (), {"boxes": self.boxes})()]


def test_crop_offset_added_back():
    """v4: a box at crop (10, 20) comes out at (x0 + 10, y0 + 20) in the full frame."""
    np = pytest.importorskip("numpy")
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    model = _FakeModel([_FakeBox([5.0, 15.0, 15.0, 25.0])])  # centre (10, 20) in the crop
    dets = kbd.detect_on_crop(model, frame, hoop_x=600.0, hoop_y=150.0)
    x0, y0, x1, y1 = kbd.crop_bounds(600.0, 150.0, 1280, 720)
    assert (x0, y0, x1, y1) == (340, 0, 860, 390)  # y0 clamps at the top edge, as v6_ball does
    assert len(dets) == 1
    assert dets[0]["x_center"] == x0 + 10.0 and dets[0]["y_center"] == y0 + 20.0
    assert model.calls == [{"shape": (390, 520, 3), "conf": 0.28, "imgsz": 640}]


def test_crop_keeps_every_box():
    """D1 keeps every detection: no single-pick, no 220 px filter."""
    np = pytest.importorskip("numpy")
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    boxes = [_FakeBox([0.0, 0.0, 10.0, 10.0], 0.3), _FakeBox([500.0, 400.0, 510.0, 410.0], 0.95)]
    dets = kbd.detect_on_crop(_FakeModel(boxes), frame, hoop_x=1000.0, hoop_y=300.0)
    assert len(dets) == 2


def test_truth_not_touched_by_arc_or_rule():
    """Spec §7: result may be read ONLY by scoring/report — not extract/arc/rule."""
    hoop = [100.0, 100.0, 50.0, 40.0]
    # Parabolic approach into rim (y down, a>0 in absolute frames)
    tag_frame = 1000
    anchor = 1010
    ball = []
    for off in range(-5, 8):
        fr = tag_frame + off
        # fake saved point that sits on a hand (x=40) while real ball is near hoop_x
        ball.append([off, 40.0, 100.0 + off * 5.0])
    bodd = [[20, 200.0, 250.0]]
    track = _track_base(ball=ball, bodd=bodd, hoop=hoop, result="make")

    # Build candidates: real ball near hoop on before-window frames; wrong saved point elsewhere
    cands = {}
    for off in range(-5, 1):
        fr = tag_frame + off
        # real ball on a clean parabola through the hoop
        y = 40.0 + 0.4 * (fr - (anchor - 8)) ** 2
        x = 100.0 + 0.1 * (fr - anchor)
        cands[fr] = [
            {"x": 40.0, "y": 100.0 + off * 5.0, "confidence": 0.3},  # hand/rim false
            {"x": x, "y": y, "confidence": 0.9},  # real ball
        ]

    track_with_result = copy.deepcopy(track)
    # Pass tracks with result REMOVED through arc and rule
    stripped = {k: v for k, v in track.items() if k != "result"}
    assert "result" not in stripped

    modified, meta = kbd.apply_arc_replacements(
        stripped,
        tag_frame=tag_frame,
        anchor_frame=anchor,
        cands_by_frame=cands,
    )
    assert "result" not in modified
    pred, details = kbd.decide_shot(
        modified,
        switch_a7=False,
        switch_a8=False,
        switch_a4=False,
        switch_c4=False,
    )
    assert isinstance(pred, bool)
    # original untouched
    assert track_with_result["result"] == "make"
    assert track_with_result["bodd"] == bodd


def test_arc_picks_real_ball_over_false_saved(tmp_path):
    hoop = [200.0, 150.0, 60.0, 50.0]
    tag_frame = 500
    anchor = 510
    fps = 25.0
    # saved track stuck on a false object (x far left)
    ball = [[off, 50.0, 120.0 + off * 3] for off in range(-10, 5)]
    bodd = [[30, 300.0, 400.0], [31, 302.0, 410.0]]
    track = _track_base(ball=ball, bodd=copy.deepcopy(bodd), hoop=hoop)

    cands: dict = {}
    # Enough real-ball candidates in before window for RANSAC (min 4)
    for fr in range(anchor - 12, anchor + 1):
        t_rel = fr - (anchor - 10)
        y = 80.0 + 0.35 * t_rel * t_rel
        x = 200.0
        cands[fr] = [
            {"x": 50.0, "y": 120.0, "confidence": 0.4},
            {"x": x, "y": y, "confidence": 0.95},
        ]
    # after window: line of real detections
    for fr in range(anchor + 1, anchor + 10):
        cands[fr] = [{"x": 200.0, "y": 150.0 + (fr - anchor) * 8.0, "confidence": 0.9}]

    stripped = {k: v for k, v in track.items() if k != "result"}
    modified, meta = kbd.apply_arc_replacements(
        stripped,
        tag_frame=tag_frame,
        anchor_frame=anchor,
        cands_by_frame=cands,
    )
    assert modified["bodd"] == bodd
    # At least one before-window frame should have been replaced toward hoop_x≈200
    chosen = meta.get("chosen_by_frame") or {}
    assert chosen, "expected some arc inliers"
    xs = [v["x"] for v in chosen.values()]
    assert any(abs(x - 200.0) < 30.0 for x in xs)

    # No invented points: every new/replaced ball point in windows must match a candidate
    cand_xy = set()
    for fr, lst in cands.items():
        for d in lst:
            cand_xy.add((fr, round(d["x"], 3), round(d["y"], 3)))
    window = set(range(anchor - 15, anchor + 13))
    for pt in modified["ball"]:
        abs_fr = tag_frame + int(pt[0])
        if abs_fr not in window:
            continue
        if abs_fr not in chosen:
            continue
        key = (abs_fr, round(pt[1], 3), round(pt[2], 3))
        assert key in cand_xy, f"invented point {key} not in candidates"

    # Write tiny candidates.json for CLI-shaped payload (3 shots)
    _write_three_shot_candidates(tmp_path, tag_frame, anchor, hoop, cands, ball, bodd)


def test_no_candidates_flags_ball_not_detected():
    hoop = [100.0, 100.0, 50.0, 40.0]
    tag_frame = 200
    anchor = 210
    ball = [[0, 100.0, 90.0], [1, 100.0, 95.0], [2, 100.0, 105.0]]
    track = _track_base(ball=ball, bodd=[], hoop=hoop)
    stripped = {k: v for k, v in track.items() if k != "result"}
    modified, meta = kbd.apply_arc_replacements(
        stripped,
        tag_frame=tag_frame,
        anchor_frame=anchor,
        cands_by_frame={},  # no candidates
    )
    assert modified["ball"] == ball  # unchanged
    rows, counts = kbd.build_diagnostic_rows(
        stripped,
        tag_frame=tag_frame,
        anchor_frame=anchor,
        anchor_reason="crossing",
        cands_by_frame={},
        chosen_by_frame={},
        hoop_x=100.0,
        hoop_y=100.0,
        hoop_w=50.0,
        t_ms=1000,
    )
    assert counts["ball_not_detected"] > 0
    assert any(r["flag"] == "ball_not_detected" for r in rows)


def test_nothing_changes_when_saved_already_on_arc():
    hoop = [100.0, 100.0, 50.0, 40.0]
    tag_frame = 300
    anchor = 310
    # saved points already on a simple parabola / line that candidates will match
    ball = []
    cands = {}
    for off in range(-8, 9):
        fr = tag_frame + off
        y = 60.0 + 0.4 * (off + 8) ** 2
        x = 100.0
        ball.append([off, x, y])
        cands[fr] = [{"x": x, "y": y, "confidence": 0.99}]
    bodd = [[40, 150.0, 300.0]]
    track = _track_base(ball=ball, bodd=copy.deepcopy(bodd), hoop=hoop)
    stripped = {k: v for k, v in track.items() if k != "result"}
    modified, meta = kbd.apply_arc_replacements(
        stripped,
        tag_frame=tag_frame,
        anchor_frame=anchor,
        cands_by_frame=cands,
    )
    assert modified["bodd"] == bodd
    # Outside windows unchanged
    outside_off = 40  # far after window
    # ensure we didn't invent that offset
    assert all(int(pt[0]) != outside_off for pt in modified["ball"])
    # frames outside windows: original offsets outside windows keep saved coords
    window_abs = set(range(anchor - 15, anchor + 13))
    orig_by_off = {int(pt[0]): pt for pt in ball}
    for pt in modified["ball"]:
        abs_fr = tag_frame + int(pt[0])
        if abs_fr in window_abs:
            continue
        o = orig_by_off[int(pt[0])]
        assert pt[1] == o[1] and pt[2] == o[2]


def test_outside_window_keeps_saved_and_bodd_immutable():
    hoop = [100.0, 100.0, 50.0, 40.0]
    tag_frame = 0
    anchor = 20
    ball = [
        [-30, 10.0, 10.0],  # outside before window
        [0, 100.0, 80.0],
        [5, 100.0, 100.0],
        [40, 11.0, 11.0],  # outside after window
    ]
    bodd = [[100, 1.0, 2.0]]
    track = _track_base(ball=ball, bodd=copy.deepcopy(bodd), hoop=hoop)
    # candidates only near anchor that would "want" to rewrite far points if we wrongly replaced whole list
    cands = {
        fr: [{"x": 999.0, "y": 999.0, "confidence": 0.99}]
        for fr in range(anchor - 2, anchor + 3)
    }
    stripped = {k: v for k, v in track.items() if k != "result"}
    modified, _ = kbd.apply_arc_replacements(
        stripped,
        tag_frame=tag_frame,
        anchor_frame=anchor,
        cands_by_frame=cands,
    )
    by_off = {int(pt[0]): pt for pt in modified["ball"]}
    assert by_off[-30][1] == 10.0 and by_off[-30][2] == 10.0
    assert by_off[40][1] == 11.0 and by_off[40][2] == 11.0
    assert modified["bodd"] == bodd
    # mutate check: original bodd list identity content
    assert track["bodd"] == [[100, 1.0, 2.0]]


def test_seed_makes_two_runs_identical():
    hoop = [100.0, 100.0, 50.0, 40.0]
    tag_frame = 100
    anchor = 115
    ball = [[off, 50.0, 90.0 + off] for off in range(-15, 10)]
    track = _track_base(ball=ball, bodd=[[50, 1.0, 2.0]], hoop=hoop)
    cands = {}
    for fr in range(anchor - 15, anchor + 13):
        cands[fr] = [
            {"x": 50.0 + (fr % 3), "y": 90.0 + (fr - tag_frame), "confidence": 0.5},
            {"x": 100.0, "y": 70.0 + 0.3 * (fr - (anchor - 10)) ** 2, "confidence": 0.9},
            {"x": 80.0, "y": 100.0, "confidence": 0.6},
        ]
    stripped = {k: v for k, v in track.items() if k != "result"}
    m1, meta1 = kbd.apply_arc_replacements(
        stripped, tag_frame=tag_frame, anchor_frame=anchor, cands_by_frame=cands, seed=42
    )
    m2, meta2 = kbd.apply_arc_replacements(
        stripped, tag_frame=tag_frame, anchor_frame=anchor, cands_by_frame=cands, seed=42
    )
    assert m1["ball"] == m2["ball"]
    assert meta1["chosen_by_frame"] == meta2["chosen_by_frame"]
    assert meta1["before_params"] == meta2["before_params"]
    assert meta1["after_params"] == meta2["after_params"]


def test_cap_keeps_top_3_by_confidence():
    cands = [
        {"x": 1, "y": 1, "confidence": 0.2},
        {"x": 2, "y": 2, "confidence": 0.9},
        {"x": 3, "y": 3, "confidence": 0.5},
        {"x": 4, "y": 4, "confidence": 0.8},
    ]
    capped, over = kbd.cap_top_candidates(cands, kbd.CANDIDATE_CAP)
    assert over is True
    assert len(capped) == 3
    assert [c["confidence"] for c in capped] == [0.9, 0.8, 0.5]


def test_handmade_candidates_json_roundtrip(tmp_path):
    """Steps 2–8 shape: tiny candidates.json with 3 shots."""
    path = _write_three_shot_candidates(tmp_path, 1000, 1010, [100.0, 100.0, 50.0, 40.0], {}, [], [])
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["n_shots"] == 3
    assert data["mapping_check"]["rate"] >= 0.90
    films_t = {(s["film"], s["t"]) for s in data["shots"]}
    assert len(films_t) == 3


def test_run_arc_and_rule_strips_result():
    hoop = [100.0, 100.0, 50.0, 40.0]
    tag_frame = 0
    t_ms = 0
    fps = 25.0
    # minimal track that decide_shot can run (may return miss — ok)
    ball = [[i, 100.0, 80.0 + i * 5] for i in range(6)]
    track = _track_base(ball=ball, bodd=[], hoop=hoop, result="miss")
    out = kbd.run_arc_and_rule_on_shot(track, t_ms=t_ms, fps=fps, cands_by_frame={})
    assert "old_pred" in out and "new_pred" in out
    assert out["modified_bodd"] == []


def _write_three_shot_candidates(
    tmp_path: Path,
    tag_frame: int,
    anchor: int,
    hoop,
    cands_shot1,
    ball_shot1,
    bodd_shot1,
) -> Path:
    """Three shots: (1) false-cand arc, (2) no cands, (3) unchanged."""
    def frames_dict(cands):
        return {
            str(fr): {"candidates": list(lst), "raw_basketball": list(lst), "decode_ok": True}
            for fr, lst in cands.items()
        }

    # shot 1 — arc case
    if not cands_shot1:
        cands_shot1 = {
            anchor - i: [{"x": 100.0, "y": 80.0 + i, "confidence": 0.9}]
            for i in range(6)
        }
    shot1 = {
        "film": "test_film",
        "t": 1000,
        "fps": 25.0,
        "tag_frame": tag_frame,
        "anchor_frame": anchor,
        "anchor_reason": "crossing",
        "hoop": hoop,
        "frames": frames_dict(cands_shot1),
    }
    # shot 2 — no candidates
    shot2 = {
        "film": "test_film",
        "t": 2000,
        "fps": 25.0,
        "tag_frame": 2000,
        "anchor_frame": 2010,
        "anchor_reason": "no_crossing_closest_ball",
        "hoop": hoop,
        "frames": {
            str(2010): {"candidates": [], "raw_basketball": [], "decode_ok": True},
        },
    }
    # shot 3 — candidates match saved (noop-ish)
    shot3_cands = {
        3010: [{"x": 100.0, "y": 100.0, "confidence": 0.99}],
    }
    shot3 = {
        "film": "test_film",
        "t": 3000,
        "fps": 25.0,
        "tag_frame": 3000,
        "anchor_frame": 3010,
        "anchor_reason": "crossing",
        "hoop": hoop,
        "frames": frames_dict(shot3_cands),
    }
    payload = {
        "mapping_check": {
            "hits": 10,
            "total": 10,
            "rate": 1.0,
            "per_film": {"test_film": {"hits": 10, "total": 10, "rate": 1.0}},
            "match_px": 3,
            "min_rate": 0.90,
        },
        "frames_over_cap": 0,
        "n_shots": 3,
        "shots": [shot1, shot2, shot3],
    }
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def test_mapping_gate_message_constant():
    assert kbd.MAPPING_MIN_MATCH_RATE == 0.90


# --- spec 23 v3: --mapping-proof-json (default behaviour unchanged) ------------------------
def _cands_with_rate(tmp_path, name, rate, **change):
    src = _write_three_shot_candidates(tmp_path, 1000, 1010, [100.0, 100.0, 50.0, 40.0], {}, [], [])
    data = json.loads(src.read_text(encoding="utf-8"))
    data["mapping_check"]["rate"] = rate
    data["constants"] = {"BALL_CONFIDENCE": 0.28}
    data.update(change)
    out = tmp_path / name
    out.write_text(json.dumps(data), encoding="utf-8")
    return out


def _no_tracks(monkeypatch):
    monkeypatch.setattr(kbd, "load_build_shot_list", lambda tracks_dir: ([], {}, None))
    monkeypatch.setattr(kbd, "prove_noop_identity", lambda shots, tracks: None)


def _run(tmp_path, cand, proof=None):
    return kbd.step_arc_rule_report(candidates_json=cand, tracks_dir=None, out_json=tmp_path / "r.json",
                                    out_md=tmp_path / "r.md", mapping_proof_json=proof)


def test_without_proof_a_low_rate_still_stops(tmp_path, monkeypatch):
    _no_tracks(monkeypatch)
    with pytest.raises(SystemExit, match="MAPPING CHECK GATE FAILED"):
        _run(tmp_path, _cands_with_rate(tmp_path, "new.json", 0.8629))


def test_good_proof_lets_low_rate_go_on_and_records_agreement(tmp_path, monkeypatch):
    _no_tracks(monkeypatch)
    new = _cands_with_rate(tmp_path, "new.json", 0.8629)
    proof = _cands_with_rate(tmp_path, "proof.json", 0.9995)
    assert _run(tmp_path, new, proof) == 0
    out = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert out["agreement_with_v6"] == 0.8629


def test_no_agreement_key_without_proof(tmp_path, monkeypatch):
    _no_tracks(monkeypatch)
    assert _run(tmp_path, _cands_with_rate(tmp_path, "new.json", 0.95)) == 0
    assert "agreement_with_v6" not in json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))


def test_proof_below_gate_stops(tmp_path, monkeypatch):
    _no_tracks(monkeypatch)
    with pytest.raises(SystemExit, match="MAPPING CHECK GATE FAILED"):
        _run(tmp_path, _cands_with_rate(tmp_path, "new.json", 0.99), _cands_with_rate(tmp_path, "proof.json", 0.85))


def test_proof_with_other_constants_or_shots_stops(tmp_path, monkeypatch):
    _no_tracks(monkeypatch)
    new = _cands_with_rate(tmp_path, "new.json", 0.8629)
    bad_const = _cands_with_rate(tmp_path, "p1.json", 0.9995, constants={"BALL_CONFIDENCE": 0.20})
    with pytest.raises(SystemExit, match="MAPPING PROOF MISMATCH"):
        _run(tmp_path, new, bad_const)
    data = json.loads(new.read_text(encoding="utf-8"))
    bad_shots = _cands_with_rate(tmp_path, "p2.json", 0.9995, shots=data["shots"][:2], n_shots=2)
    with pytest.raises(SystemExit, match="MAPPING PROOF MISMATCH"):
        _run(tmp_path, new, bad_shots)
    same_n_other_t = [dict(s) for s in data["shots"]]
    same_n_other_t[0]["t"] = 999
    bad_t = _cands_with_rate(tmp_path, "p3.json", 0.9995, shots=same_n_other_t)
    with pytest.raises(SystemExit, match="MAPPING PROOF MISMATCH"):
        _run(tmp_path, new, bad_t)


# --- Fall-through guard tests (spec §3, §4) -------------------------------------


def _make_track(ball, bodd=None, hoop=None, result="make"):
    if hoop is None:
        hoop = [100.0, 100.0, 50.0, 40.0]  # x, y, w, area
    if bodd is None:
        bodd = []
    return {
        "t": 1000,
        "result": result,
        "hoop": hoop,
        "ball": ball,
        "bodd": bodd,
    }


def test_fall_through_check_straight_drop_inside_rim_passes():
    """Straight drop inside rim (|x - hoop_x| < 0.5*hoop_w) -> None (pass)."""
    hoop_x, hoop_y, hoop_w = 100.0, 100.0, 50.0
    scale_y = 1.0
    cross_frame = 10
    # ball above rim at frame 9, then crossing at 10, then 3+ points below rim within 0.5*hoop_w
    ball = [
        (9, 100.0, 90.0),   # above rim
        (10, 100.0, 100.0), # crossing
        (11, 100.0, 110.0), # below rim, centered
        (12, 100.0, 120.0),
        (13, 100.0, 130.0),
    ]
    assert fall_through_check(ball, cross_frame, hoop_x, hoop_y, hoop_w, scale_y) is None


def test_fall_through_check_one_point_at_half_hoop_w_fails_outside_rim():
    """One point at exactly 0.5*hoop_w -> 'outside_rim' (>= is fail)."""
    hoop_x, hoop_y, hoop_w = 100.0, 100.0, 50.0
    scale_y = 1.0
    cross_frame = 10
    ball = [
        (9, 100.0, 90.0),
        (10, 125.0, 100.0),  # crossing at 0.5*hoop_w (125 = 100 + 25)
        (11, 125.0, 110.0),
        (12, 125.0, 120.0),
        (13, 125.0, 130.0),
    ]
    assert fall_through_check(ball, cross_frame, hoop_x, hoop_y, hoop_w, scale_y) == "outside_rim"


def test_fall_through_check_rises_after_going_deeper_fails_went_up():
    """Rises 6px ( > 5*scale_y ) after going deeper -> 'went_up'."""
    hoop_x, hoop_y, hoop_w = 100.0, 100.0, 50.0
    scale_y = 1.0
    cross_frame = 10
    ball = [
        (9, 100.0, 90.0),
        (10, 100.0, 100.0),
        (11, 100.0, 120.0),  # depth 20
        (12, 100.0, 114.0),  # rose 6px (> 5)
        (13, 100.0, 130.0),
    ]
    assert fall_through_check(ball, cross_frame, hoop_x, hoop_y, hoop_w, scale_y) == "went_up"


def test_fall_through_check_only_two_points_below_rim_fails_short_fall():
    """Only 2 points below rim (min 3) -> 'short_fall'."""
    hoop_x, hoop_y, hoop_w = 100.0, 100.0, 50.0
    scale_y = 1.0
    cross_frame = 10
    ball = [
        (9, 100.0, 90.0),
        (10, 100.0, 100.0),
        (11, 100.0, 110.0),
        (12, 100.0, 120.0),  # only 2 points strictly below rim (frames 11,12)
    ]
    assert fall_through_check(ball, cross_frame, hoop_x, hoop_y, hoop_w, scale_y) == "short_fall"


def test_fall_through_check_first_point_below_rim_with_no_earlier_above_fails_no_ball_crossing():
    """First point after crossing is below rim but no earlier ball point above rim -> 'no_ball_crossing'."""
    hoop_x, hoop_y, hoop_w = 100.0, 100.0, 50.0
    scale_y = 1.0
    cross_frame = 10
    ball = [
        (10, 100.0, 100.0),  # crossing frame, but no point before with y < hoop_y
        (11, 100.0, 110.0),
        (12, 100.0, 120.0),
        (13, 100.0, 130.0),
    ]
    assert fall_through_check(ball, cross_frame, hoop_x, hoop_y, hoop_w, scale_y) == "no_ball_crossing"


def test_fall_through_check_empty_G_fails_no_ball_crossing():
    """G empty (no points below rim within 180px) -> 'no_ball_crossing'."""
    hoop_x, hoop_y, hoop_w = 100.0, 100.0, 50.0
    scale_y = 1.0
    cross_frame = 10
    ball = [
        (9, 100.0, 90.0),
        (10, 100.0, 100.0),  # crossing
        # no points with y > hoop_y
    ]
    assert fall_through_check(ball, cross_frame, hoop_x, hoop_y, hoop_w, scale_y) == "no_ball_crossing"


def test_decide_shot_switch_false_equals_current_on_make_track():
    """decide_shot with switch_fall_through=False equals current result on a make track."""
    hoop = [100.0, 100.0, 50.0, 40.0]
    # A simple make track that passes all existing checks
    ball = [
        (0, 100.0, 50.0),
        (1, 100.0, 70.0),
        (2, 100.0, 90.0),
        (3, 100.0, 100.0),  # crossing
        (4, 100.0, 110.0),
        (5, 100.0, 120.0),
        (6, 100.0, 130.0),
        (7, 100.0, 140.0),
        (8, 100.0, 150.0),
        (9, 100.0, 160.0),
        (10, 100.0, 170.0),
    ]
    bodd = []
    track = _make_track(ball, bodd, hoop, "make")
    pred_off, det_off = decide_shot(track, switch_fall_through=False)
    pred_on, det_on = decide_shot(track, switch_fall_through=True)
    # With switch off, should be make (assuming it passes other checks)
    # With switch on and this clean track, should also be make
    assert pred_off == pred_on
    assert pred_off is True


def test_decide_shot_switch_false_equals_current_on_miss_track():
    """decide_shot with switch_fall_through=False equals current result on a miss track."""
    hoop = [100.0, 100.0, 50.0, 40.0]
    # A miss track (no crossing)
    ball = [
        (0, 100.0, 50.0),
        (1, 100.0, 60.0),
        (2, 100.0, 70.0),
    ]
    bodd = []
    track = _make_track(ball, bodd, hoop, "miss")
    pred_off, det_off = decide_shot(track, switch_fall_through=False)
    pred_on, det_on = decide_shot(track, switch_fall_through=True)
    assert pred_off == pred_on
    assert pred_off is False


def test_decide_shot_switch_true_never_turns_miss_into_make():
    """switch_fall_through=True never turns a miss into a make."""
    hoop = [100.0, 100.0, 50.0, 40.0]
    # Various miss tracks
    miss_tracks = [
        # No crossing
        _make_track([(0, 100.0, 50.0), (1, 100.0, 60.0)], hoop=hoop, result="miss"),
        # Crossing but ball goes up
        _make_track(
            [(0, 100.0, 90.0), (1, 100.0, 100.0), (2, 100.0, 95.0), (3, 100.0, 110.0)],
            hoop=hoop, result="miss"
        ),
        # Crossing but outside rim
        _make_track(
            [(0, 150.0, 90.0), (1, 150.0, 100.0), (2, 150.0, 110.0), (3, 150.0, 120.0)],
            hoop=hoop, result="miss"
        ),
    ]
    for track in miss_tracks:
        pred, _ = decide_shot(track, switch_fall_through=True)
        assert pred is False, f"Expected miss, got make on track: {track['ball']}"
