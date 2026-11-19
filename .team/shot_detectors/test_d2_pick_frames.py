"""Tests for d2_pick_frames.py (spec .team/specs/22_d2_label_job_spec.md). No video, no models."""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
import d2_pick_frames as d  # noqa: E402


def cand(film, fn, status="SEEN", seen=None):
    hoop = [600.0, 300.0, 40.0, 30.0]
    return {"film": film, "frame_number": fn, "time_seconds": fn / 25, "crop_box": [340, 100, 860, 540],
            "status": status, "window_start": fn - 10, "seen_frame": fn if seen is None else seen,
            "hoop": hoop, "ball": [610.0, 290.0]}


def pool(n_per_film=400):
    out = []
    for f in d.FILMS:
        for i in range(n_per_film):
            fn = 10000 + i * 5
            out.append(cand(f, fn, "SEEN") if i % 2 == 0 else cand(f, fn, "LOST", seen=fn - 2))
    return out


# --- geometry -------------------------------------------------------------------------
def test_zone_edges():
    assert d.in_zone(600 + 120, 300, 600, 300, 40)          # 3.0 x hoop_w exactly
    assert not d.in_zone(600 + 121, 300, 600, 300, 40)
    assert d.in_zone(600, 300 - 160, 600, 300, 40)           # 4.0 x hoop_w above
    assert not d.in_zone(600, 300 - 161, 600, 300, 40)
    assert d.in_zone(600, 600, 600, 300, 40)                 # +300 px below
    assert not d.in_zone(600, 601, 600, 300, 40)


def test_crop_box_matches_d1_and_clamps():
    sys.path.insert(0, os.path.dirname(__file__))
    import keep_ball_detections as k
    for hx, hy in [(100.7, 50.2), (640.4, 360.9), (1250.5, 700.1)]:
        assert d.crop_box(hx, hy, 1280, 720) == k.crop_bounds(hx, hy, 1280, 720)
    assert d.crop_box(10, 10, 1280, 720)[:2] == (0, 0)


def test_median_hoop():
    assert d.median_hoop([(1, 2, 3, 4), (3, 4, 5, 6), (100, 100, 100, 100)]) == (3.0, 4.0, 5.0, 6.0)


# --- holdout (spec 1 binding note) -------------------------------------------------------
def test_holdout_read_from_json_with_film_fps():
    h = d.holdout_frames(25)
    assert h == [5808, 15172, 24538, 33902, 43268, 52632, 61998, 71362, 80728, 90092]
    assert d.holdout_frames(30) == [int(round(ms * 30 / 1000)) for ms in
                                    [232300, 606900, 981500, 1356100, 1730700, 2105300, 2479900, 2854500, 3229100, 3603700]]


def test_holdout_uses_the_file(tmp_path):
    p = tmp_path / "h.json"
    p.write_text(json.dumps([["jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334", "x", 1000],
                             ["jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334", "y", 9000]]))
    assert d.holdout_frames(25, p) == [25]


def test_near_holdout_is_inclusive_at_5_seconds():
    assert d.near_holdout(5808 + 125, [5808], 25)
    assert not d.near_holdout(5808 + 126, [5808], 25)


# --- SEEN / LOST (spec 3) ----------------------------------------------------------------
def test_lost_only_after_last_seen():
    flags = [False, True, False, False, True] + [False] * 12
    got = d.classify_window(flags)
    assert [(i, s) for i, s, _ in got if s == "SEEN"] == [(1, "SEEN"), (4, "SEEN")]
    lost = [i for i, s, _ in got if s == "LOST"]
    assert lost == list(range(5, 13))                   # first 8 after the last SEEN (4)
    assert all(last == 4 for _, s, last in got if s == "LOST")
    assert 2 not in lost and 3 not in lost              # gap between SEENs is not LOST


def test_lost_cut_at_window_end_and_none_without_seen():
    assert [i for i, s, _ in d.classify_window([False, True, False, False]) if s == "LOST"] == [2, 3]
    assert d.classify_window([False] * 10) == []


# --- quotas (spec 3) ---------------------------------------------------------------------
def test_base_quotas():
    q = d.base_quotas()
    assert list(q.values()) == [86, 86, 86, 86, 86, 85, 85] and sum(q.values()) == 600


def test_quota_shortfall_spread():
    y = {f: 1000 for f in d.FILMS}
    y[d.FILMS[0]] = 50
    q = d.compute_quotas(y)
    assert q[d.FILMS[0]] == 50 and sum(q.values()) == 600
    assert max(q[f] for f in d.FILMS[1:]) - min(q[f] for f in d.FILMS[1:]) <= 1


# --- pick + the 8 checks of spec 6 -------------------------------------------------------
def picked_ok():
    c = pool()
    q = d.compute_quotas({f: 400 for f in d.FILMS})
    return c, q, d.pick_frames(c, q)


def test_pick_half_seen_half_lost_gap_and_seed():
    c, q, p = picked_ok()
    assert len(p) == 600
    for f in d.FILMS:
        mine = [x for x in p if x["film"] == f]
        assert sum(x["status"] == "SEEN" for x in mine) == q[f] // 2
        fr = sorted(x["frame_number"] for x in mine)
        assert all(b - a >= 3 for a, b in zip(fr, fr[1:]))
    assert d.pick_frames(c, q) == p                      # seed 42 twice


def test_pick_never_relaxes_gap():
    f = d.FILMS[0]
    tight = [cand(f, 100 + i) for i in range(10)]      # frames 1 apart: only 4 fit 3 apart
    got = d.pick_film(tight, 10, random.Random(42))
    assert len(got) <= 4


def test_verify_passes_good_pick():
    _, q, p = picked_ok()
    fps = {f: 25.0 for f in d.FILMS}
    assert d.verify(p, q, fps, d.holdout_frames(25), repick=list(p)) == []


def test_verify_catches_each_failure():
    _, q, p = picked_ok()
    fps = {f: 25.0 for f in d.FILMS}
    h = d.holdout_frames(25)

    def fails(mut, prefix, repick=None):
        pp = [dict(x) for x in p]
        mut(pp)
        bad = d.verify(pp, q, fps, h, repick)
        assert any(b.startswith(prefix) for b in bad), (prefix, bad)

    fails(lambda pp: pp[0].update(film="LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4"), "1/7")   # 1, 7
    def holdout_hit(pp):
        x = next(x for x in pp if x["film"] == d.HOLDOUT_FILM)
        x["frame_number"] = 5808 + 100
    fails(holdout_hit, "2")                                                                    # 2
    fails(lambda pp: pp.pop(), "3")                                                            # 3
    fails(lambda pp: None, "4", repick=list(reversed(p)))                                      # 4
    fails(lambda pp: pp[0].update(film=d.FILMS[1]), "5")                                       # 5
    fails(lambda pp: next(x for x in pp if x["status"] == "SEEN").update(ball=[0.0, 0.0]), "6")  # 6
    def lost_far(pp):
        x = next(x for x in pp if x["status"] == "LOST")
        x["seen_frame"] = x["frame_number"] - 9
    fails(lost_far, "8")                                                                       # 8


# --- label page (spec 5) -----------------------------------------------------------------
def test_label_page_is_self_contained():
    meta = [{"film": d.FILMS[0], "frame_number": 95, "time_seconds": 3.1667, "crop_box": [0, 0, 520, 440]}]
    html = d.make_label_html(meta)
    assert "__FRAMES__" not in html and '"frame_number": 95' in html
    assert "fetch(" not in html and "http" not in html.replace("http-equiv", "")   # opens from a folder, no internet
    for needed in ("ArrowLeft", "ArrowRight", "pointerdown", "No ball", "Export labels", "labels.json",
                   "localStorage", " of "):
        assert needed in html, needed
    assert d.crop_name(d.FILMS[0], 95) == "LIBERTY_A_v_HSB_H1_20260809_221334_fr000095.jpg"
