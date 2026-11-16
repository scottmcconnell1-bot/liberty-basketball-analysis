"""Synthetic tests for rim_first_make_miss (spec 44/45/46). No video, no models."""
from __future__ import annotations

import argparse
import copy
import json
import sys
import types
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# collect_q4_bodd imports ultralytics at module load; stub if absent (WSL/system py).
if "ultralytics" not in sys.modules:
    _ultra = types.ModuleType("ultralytics")

    class _StubYOLO:  # pragma: no cover - import shim only
        def __init__(self, *args, **kwargs):
            self.names = {}

    _ultra.YOLO = _StubYOLO
    sys.modules["ultralytics"] = _ultra

import collect_q4_bodd as q4  # noqa: E402
import keep_ball_detections as kbd  # noqa: E402
import rim_first_make_miss as rfmm  # noqa: E402


def _d1_tracks(tmp_path: Path) -> Path:
    tracks_path = tmp_path / "tracks.json"
    tracks_path.write_text(
        json.dumps(
            [
                {
                    "t": 1000,
                    "moment_t_ms": 2000,
                    "hoop": [1.0, 2.0, 3.0, 4.0],
                    "ball": [(0, 1.0, 2.0)],
                    "bodd": [],
                }
            ]
        ),
        encoding="utf-8",
    )
    return tracks_path


def _d1_args(
    tmp_path: Path,
    *,
    with_proof: bool = False,
    film_scale: bool = False,
    scaled_crop: bool = False,
    crop_scale_json: Optional[Path] = None,
    tracks_json: Optional[Path] = None,
) -> argparse.Namespace:
    proof = None
    if with_proof:
        proof = tmp_path / "mapping_proof.json"
        proof.write_text("{}", encoding="utf-8")
    return argparse.Namespace(
        tracks_json=tracks_json if tracks_json is not None else _d1_tracks(tmp_path),
        out_dir=tmp_path / "d1_out",
        film_name="test_film",
        video_rel="uploads/example.mp4",
        weights=tmp_path / "weights.pt",
        mapping_proof_json=proof,
        film_scale=film_scale,
        scaled_crop=scaled_crop,
        crop_scale_json=crop_scale_json,
    )


def _fake_main(
    *,
    extract: Optional[Callable[[Path], Any]] = None,
    report: Optional[Callable[[Path], Any]] = None,
) -> Callable[[Optional[List[str]]], int]:
    def _main(argv: Optional[List[str]] = None) -> int:
        argv = list(argv or [])
        step = argv[argv.index("--step") + 1]
        out_json = Path(argv[argv.index("--out-json") + 1])
        if step == "extract":
            if extract is None:
                out_json.write_text("[]", encoding="utf-8")
                return 0
            return int(extract(out_json) or 0)
        if step == "arc-rule-report":
            if report is None:
                out_json.write_text(json.dumps({"shots": []}), encoding="utf-8")
                return 0
            return int(report(out_json) or 0)
        raise AssertionError(f"unexpected step {step}")

    return _main


def test_vote_table_make_coach_miss_no_track(tmp_path):
    tracks = [
        {
            "t": 1000,
            "moment_t_ms": 2000,
            "hoop": [1.0, 2.0, 3.0, 4.0],
            "ball": [(0, 1.0, 2.0)],
            "bodd": [],
        },
        {
            "t": 2000,
            "moment_t_ms": 3000,
            "hoop": [1.0, 2.0, 3.0, 4.0],
            "ball": [(0, 1.0, 2.0)],
            "bodd": [],
        },
        {
            "t": 3000,
            "moment_t_ms": 4000,
            "hoop": [1.0, 2.0, 3.0, 4.0],
            "ball": [(0, 1.0, 2.0)],
            "bodd": [],
        },
        {
            "t": 4000,
            "moment_t_ms": 5000,
            "hoop": None,
            "ball": [],
            "bodd": [],
        },
        {
            "t": 5000,
            "moment_t_ms": 6000,
            "hoop": [1.0, 2.0, 3.0, 4.0],
            "ball": [],
            "bodd": [(0, 1.0, 2.0)],
        },
    ]
    v6 = {
        "shots": [
            {"t": 1000, "new_pred": True, "new_reason": "a"},
            {"t": 2000, "new_pred": True, "new_reason": "b"},
            {"t": 3000, "new_pred": False, "new_reason": "c"},
        ]
    }
    d2 = {
        "shots": [
            {"t": 1000, "new_pred": True, "new_reason": "d"},
            {"t": 2000, "new_pred": False, "new_reason": "e"},
            {"t": 3000, "new_pred": False, "new_reason": "f"},
        ]
    }
    rows = rfmm.build_vote_rows(tracks, v6, d2)
    by_t = {r["start_ms"]: r["call"] for r in rows}
    assert by_t[1000] == "make"
    assert by_t[2000] == "coach"
    assert by_t[3000] == "miss"
    assert by_t[4000] == "no_track"
    assert by_t[5000] == "no_track"

    out = tmp_path / "vote_out"
    rfmm.write_vote_outputs(rows, out)
    saved = json.loads((out / "make_miss.json").read_text(encoding="utf-8"))
    assert [r["call"] for r in saved] == ["make", "coach", "miss", "no_track", "no_track"]
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert "make: 1" in summary
    assert "coach: 1" in summary
    assert "miss: 1" in summary
    assert "no_track: 2" in summary


def test_missing_result_raises():
    tracks = [
        {
            "t": 1000,
            "moment_t_ms": 2000,
            "hoop": [1.0, 2.0, 3.0, 4.0],
            "ball": [(0, 1.0, 2.0)],
            "bodd": [],
        }
    ]
    v6 = {"shots": [{"t": 1000, "new_pred": True, "new_reason": "a"}]}
    d2 = {"shots": []}
    with pytest.raises(SystemExit, match="missing d2v1 result"):
        rfmm.build_vote_rows(tracks, v6, d2)


def test_start_ms_and_frame_rounding():
    assert rfmm.TRACK_LEAD_MS == 1000
    assert rfmm.start_ms_for(2500) == 1500
    assert rfmm.start_ms_for(2500, lead_ms=0) == 2500
    assert rfmm.start_frame_for(1000, 25.0) == 25
    assert rfmm.start_frame_for(1500, 25.0) == 38  # round(37.5) == 38
    assert rfmm.start_frame_for(1400, 25.0) == 35  # round(35.0) == 35


def test_tag_times_list_input(tmp_path):
    path = tmp_path / "times.json"
    path.write_text(json.dumps([100, 200, 300]), encoding="utf-8")
    assert rfmm.load_moment_times_from_tag_times(path) == [100, 200, 300]


def test_moments_input(tmp_path):
    path = tmp_path / "moments.json"
    path.write_text(
        json.dumps({"moments": [{"t_ms": 111}, {"t_ms": 222}]}),
        encoding="utf-8",
    )
    assert rfmm.load_moment_times_from_moments(path) == [111, 222]


def test_shot_list_swap_gt_make_none_skips_incomplete(tmp_path):
    tracks_path = tmp_path / "tracks.json"
    tracks = [
        {
            "t": 1000,
            "moment_t_ms": 2000,
            "hoop": [10.0, 20.0, 30.0, 40.0],
            "ball": [(0, 10.0, 20.0)],
            "bodd": [(0, 10.0, 20.0)],
        },
        {
            "t": 2000,
            "moment_t_ms": 3000,
            "hoop": None,
            "ball": [(0, 1.0, 2.0)],
            "bodd": [],
        },
        {
            "t": 3000,
            "moment_t_ms": 4000,
            "hoop": [1.0, 2.0, 3.0, 4.0],
            "ball": [],
            "bodd": [(0, 1.0, 2.0)],
        },
    ]
    tracks_path.write_text(json.dumps(tracks), encoding="utf-8")
    shots, tracks_by_film, path_by_film = rfmm.build_shot_list_from_tracks(
        tracks,
        film_name="gv",
        video_rel="uploads/example.mp4",
        tracks_path=tracks_path,
    )
    assert len(shots) == 1
    assert shots[0]["t"] == 1000
    assert shots[0]["gt_make"] is None
    assert shots[0]["quarter"] is None
    assert shots[0]["label"] is None
    assert shots[0]["player"] is None
    assert shots[0]["start"] is None
    assert shots[0]["film"] == "gv"
    assert shots[0]["video_rel"] == "uploads/example.mp4"
    assert set(tracks_by_film["gv"]) == {1000, 2000, 3000}
    assert path_by_film["gv"] == tracks_path.resolve()


def test_refuse_existing_out_paths(tmp_path):
    existing_file = tmp_path / "tracks_out.json"
    existing_file.write_text("[]", encoding="utf-8")
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        rfmm.refuse_existing_file(existing_file)

    existing_dir = tmp_path / "out_dir"
    existing_dir.mkdir()
    with pytest.raises(SystemExit, match="refusing to use existing out dir"):
        rfmm.refuse_existing_dir(existing_dir)


def test_module_source_has_no_film_tags_or_tags_path():
    src = (HERE / "rim_first_make_miss.py").read_text(encoding="utf-8")
    assert "film_tags" not in src
    assert "data/film_tags" not in src
    # No tags-file path construction; tags_rel may be the literal None assignment only.
    assert "tags_path" not in src
    assert "/tags/" not in src
    assert "\\tags\\" not in src


def test_cmd_d1_extract_mapping_gate_with_proof_continues(tmp_path, monkeypatch, capsys):
    def extract(out_json: Path) -> int:
        out_json.write_text("[]", encoding="utf-8")
        raise SystemExit("MAPPING CHECK GATE FAILED rate=0.50 < 0.90")

    monkeypatch.setattr(kbd, "main", _fake_main(extract=extract))
    args = _d1_args(tmp_path, with_proof=True)
    assert rfmm.cmd_d1(args) == 0
    assert (args.out_dir / "results.json").exists()
    out = capsys.readouterr().out
    assert "extract mapping gate stop" in out
    assert "proof file used, spec 23 v3" in out


def test_cmd_d1_extract_mapping_gate_without_proof_reraises(tmp_path, monkeypatch):
    def extract(out_json: Path) -> int:
        out_json.write_text("[]", encoding="utf-8")
        raise SystemExit("MAPPING CHECK GATE FAILED rate=0.50 < 0.90")

    monkeypatch.setattr(kbd, "main", _fake_main(extract=extract))
    args = _d1_args(tmp_path, with_proof=False)
    with pytest.raises(SystemExit, match="MAPPING CHECK GATE FAILED"):
        rfmm.cmd_d1(args)


def test_cmd_d1_hard_gate_ignored_when_results_exist(tmp_path, monkeypatch, capsys):
    def report(out_json: Path) -> int:
        out_json.write_text(json.dumps({"shots": []}), encoding="utf-8")
        raise SystemExit("HARD GATE FAILED something")

    monkeypatch.setattr(kbd, "main", _fake_main(report=report))
    args = _d1_args(tmp_path)
    assert rfmm.cmd_d1(args) == 0
    note = json.loads((args.out_dir / "wrapper_note.json").read_text(encoding="utf-8"))
    assert note["truth_absent"] is True
    assert note["ignored_exit"].startswith("HARD GATE FAILED")
    assert "truth-based gate ignored: truth absent (spec 44 V2)" in capsys.readouterr().out


def test_cmd_d1_lost_makes_ignored_when_results_exist(tmp_path, monkeypatch, capsys):
    def report(out_json: Path) -> int:
        out_json.write_text(json.dumps({"shots": []}), encoding="utf-8")
        raise SystemExit("LOST MAKES 3 of 5")

    monkeypatch.setattr(kbd, "main", _fake_main(report=report))
    args = _d1_args(tmp_path)
    assert rfmm.cmd_d1(args) == 0
    note = json.loads((args.out_dir / "wrapper_note.json").read_text(encoding="utf-8"))
    assert note["truth_absent"] is True
    assert note["ignored_exit"].startswith("LOST MAKES")
    assert "truth-based gate ignored: truth absent (spec 44 V2)" in capsys.readouterr().out


def test_cmd_d1_noop_proof_failed_reraises(tmp_path, monkeypatch):
    def report(out_json: Path) -> int:
        out_json.write_text(json.dumps({"shots": []}), encoding="utf-8")
        raise SystemExit("NO-OP PROOF FAILED detail")

    monkeypatch.setattr(kbd, "main", _fake_main(report=report))
    args = _d1_args(tmp_path)
    with pytest.raises(SystemExit, match="NO-OP PROOF FAILED"):
        rfmm.cmd_d1(args)
    assert not (args.out_dir / "wrapper_note.json").exists()


def test_cmd_d1_mapping_proof_mismatch_reraises(tmp_path, monkeypatch):
    def report(out_json: Path) -> int:
        out_json.write_text(json.dumps({"shots": []}), encoding="utf-8")
        raise SystemExit("MAPPING PROOF MISMATCH detail")

    monkeypatch.setattr(kbd, "main", _fake_main(report=report))
    args = _d1_args(tmp_path, with_proof=True)
    with pytest.raises(SystemExit, match="MAPPING PROOF MISMATCH"):
        rfmm.cmd_d1(args)
    assert not (args.out_dir / "wrapper_note.json").exists()


# --- spec 45 film scale ---


def _hoop_track(t: int, width: float, *, with_ball: bool = True) -> dict:
    return {
        "t": t,
        "moment_t_ms": t + 1000,
        "hoop": [10.0, 20.0, float(width), 40.0],
        "ball": [(0, 1.0, 2.0)] if with_ball else [],
        "bodd": [],
    }


def test_film_scale_info_odd_count_median():
    tracks = [
        _hoop_track(1, 90.0),
        _hoop_track(2, 98.0),
        _hoop_track(3, 110.0),
    ]
    info = rfmm.film_scale_info(tracks)
    assert info["film_hoop_median"] == 98.0
    assert info["film_scale"] == 1.0
    assert info["n_tracks_used"] == 3
    assert info["n_tracks_total"] == 3
    assert info["ref_hoop_w"] == rfmm.REF_HOOP_W == 98.0


def test_film_scale_info_even_count_median():
    tracks = [
        _hoop_track(1, 90.0),
        _hoop_track(2, 100.0),
        _hoop_track(3, 110.0),
        _hoop_track(4, 120.0),
    ]
    info = rfmm.film_scale_info(tracks)
    assert info["film_hoop_median"] == 105.0
    assert info["film_scale"] == 105.0 / 98.0
    assert info["n_tracks_used"] == 4
    assert info["n_tracks_total"] == 4


def test_film_scale_info_skips_tracks_without_hoop():
    tracks = [
        _hoop_track(1, 80.0),
        {"t": 2, "moment_t_ms": 3, "hoop": None, "ball": [], "bodd": []},
        {"t": 3, "moment_t_ms": 4, "hoop": [], "ball": [(0, 1.0, 2.0)], "bodd": []},
        _hoop_track(4, 100.0),
    ]
    info = rfmm.film_scale_info(tracks)
    assert info["film_hoop_median"] == 90.0
    assert info["film_scale"] == 90.0 / 98.0
    assert info["n_tracks_used"] == 2
    assert info["n_tracks_total"] == 4


def test_film_scale_info_zero_hoop_raises():
    tracks = [
        {"t": 1, "hoop": None, "ball": []},
        {"t": 2, "hoop": [], "ball": []},
    ]
    with pytest.raises(SystemExit, match="no tracks with a non-empty hoop"):
        rfmm.film_scale_info(tracks)


def test_apply_film_scale_sets_keys_on_every_track_input_unchanged():
    tracks = [
        _hoop_track(1, 98.0),
        {"t": 2, "moment_t_ms": 3, "hoop": None, "ball": [], "bodd": []},
        _hoop_track(3, 64.5, with_ball=False),
    ]
    original = copy.deepcopy(tracks)
    scaled = rfmm.apply_film_scale(tracks, 0.75)
    assert tracks == original
    assert "_court_scale_x" not in tracks[0]
    assert len(scaled) == 3
    for row in scaled:
        assert row["_court_scale_x"] == 0.75
        assert row["_court_scale_y"] == 0.75
    assert scaled[1]["hoop"] is None
    assert scaled[2]["ball"] == []
    assert scaled is not tracks
    assert scaled[0] is not tracks[0]


def test_film_scale_median_98_is_exactly_one():
    tracks = [_hoop_track(1, 98.0), _hoop_track(2, 98.0), _hoop_track(3, 98.0)]
    info = rfmm.film_scale_info(tracks)
    assert info["film_scale"] == 1.0
    scaled = rfmm.apply_film_scale(tracks, info["film_scale"])
    assert scaled[0]["_court_scale_x"] == 1.0
    assert scaled[0]["_court_scale_y"] == 1.0


def test_cmd_d1_film_scale_writes_scaled_copy_and_points_at_it(
    tmp_path, monkeypatch, capsys
):
    tracks = [
        _hoop_track(1000, 98.0),
        {"t": 2000, "moment_t_ms": 3000, "hoop": None, "ball": [], "bodd": []},
        _hoop_track(3000, 98.0, with_ball=False),
    ]
    tracks_path = tmp_path / "tracks.json"
    raw = json.dumps(tracks)
    tracks_path.write_text(raw, encoding="utf-8")
    before = tracks_path.read_bytes()

    captured: dict = {}

    def _main(argv=None):
        argv = list(argv or [])
        step = argv[argv.index("--step") + 1]
        out_json = Path(argv[argv.index("--out-json") + 1])
        if step == "extract":
            captured["films"] = list(kbd.FILMS)
            captured["shot_bundle"] = kbd.load_build_shot_list()
            captured["extract_argv"] = argv
            out_json.write_text("[]", encoding="utf-8")
            return 0
        out_json.write_text(json.dumps({"shots": []}), encoding="utf-8")
        return 0

    monkeypatch.setattr(kbd, "main", _main)
    args = _d1_args(tmp_path, film_scale=True, tracks_json=tracks_path)
    assert rfmm.cmd_d1(args) == 0

    assert tracks_path.read_bytes() == before
    scaled_path = args.out_dir / "tracks_scaled.json"
    film_path = args.out_dir / "film_scale.json"
    assert scaled_path.exists()
    assert film_path.exists()
    scaled = json.loads(scaled_path.read_text(encoding="utf-8"))
    assert len(scaled) == 3
    for row in scaled:
        assert row["_court_scale_x"] == 1.0
        assert row["_court_scale_y"] == 1.0
    info = json.loads(film_path.read_text(encoding="utf-8"))
    assert info["film_scale"] == 1.0
    assert info["film_hoop_median"] == 98.0
    assert info["n_tracks_used"] == 2
    assert info["n_tracks_total"] == 3
    assert info["ref_hoop_w"] == 98.0
    assert info["tracks_json"] == str(tracks_path.resolve())
    out = capsys.readouterr().out
    assert "film_scale=1.0" in out
    assert "n_tracks_used=2" in out

    resolved = str(scaled_path.resolve())
    assert captured["films"][0]["track_candidates"] == [resolved]
    shots, _tracks_by_film, path_by_film = captured["shot_bundle"]
    assert path_by_film["test_film"] == scaled_path.resolve()
    assert all(s["tracks_path_resolved"] == resolved for s in shots)


def test_cmd_d1_without_film_scale_unchanged_paths(tmp_path, monkeypatch):
    tracks_path = _d1_tracks(tmp_path)
    before = tracks_path.read_bytes()
    captured: dict = {}

    def _main(argv=None):
        argv = list(argv or [])
        step = argv[argv.index("--step") + 1]
        out_json = Path(argv[argv.index("--out-json") + 1])
        if step == "extract":
            captured["films"] = list(kbd.FILMS)
            captured["shot_bundle"] = kbd.load_build_shot_list()
            out_json.write_text("[]", encoding="utf-8")
            return 0
        out_json.write_text(json.dumps({"shots": []}), encoding="utf-8")
        return 0

    monkeypatch.setattr(kbd, "main", _main)
    args = _d1_args(tmp_path, film_scale=False, tracks_json=tracks_path)
    assert rfmm.cmd_d1(args) == 0
    assert tracks_path.read_bytes() == before
    assert not (args.out_dir / "tracks_scaled.json").exists()
    assert not (args.out_dir / "film_scale.json").exists()
    resolved = str(tracks_path.resolve())
    assert captured["films"][0]["track_candidates"] == [resolved]
    shots, _tb, path_by_film = captured["shot_bundle"]
    assert path_by_film["test_film"] == tracks_path.resolve()
    assert shots[0]["tracks_path_resolved"] == resolved
    assert "_court_scale_x" not in json.loads(tracks_path.read_text(encoding="utf-8"))[0]


def test_cmd_d1_film_scale_noop_proof_still_reraises(tmp_path, monkeypatch):
    def report(out_json: Path) -> int:
        out_json.write_text(json.dumps({"shots": []}), encoding="utf-8")
        raise SystemExit("NO-OP PROOF FAILED detail")

    monkeypatch.setattr(kbd, "main", _fake_main(report=report))
    args = _d1_args(tmp_path, film_scale=True)
    with pytest.raises(SystemExit, match="NO-OP PROOF FAILED"):
        rfmm.cmd_d1(args)
    assert not (args.out_dir / "wrapper_note.json").exists()


def _vote_scale_fixture(tmp_path: Path):
    tracks = [
        {
            "t": 1000,
            "moment_t_ms": 2000,
            "hoop": [1.0, 2.0, 3.0, 4.0],
            "ball": [(0, 1.0, 2.0)],
            "bodd": [],
        }
    ]
    tracks_path = tmp_path / "tracks.json"
    tracks_path.write_text(json.dumps(tracks), encoding="utf-8")
    v6_dir = tmp_path / "v6"
    d2_dir = tmp_path / "d2"
    v6_dir.mkdir()
    d2_dir.mkdir()
    v6_results = v6_dir / "results.json"
    d2_results = d2_dir / "results.json"
    payload = {
        "shots": [{"t": 1000, "new_pred": True, "new_reason": "a"}]
    }
    v6_results.write_text(json.dumps(payload), encoding="utf-8")
    d2_results.write_text(
        json.dumps(
            {"shots": [{"t": 1000, "new_pred": True, "new_reason": "b"}]}
        ),
        encoding="utf-8",
    )
    return tracks_path, v6_results, d2_results, v6_dir, d2_dir


def test_vote_copies_film_scale_when_both_equal(tmp_path):
    tracks_path, v6_results, d2_results, v6_dir, d2_dir = _vote_scale_fixture(
        tmp_path
    )
    doc = {
        "film_scale": 0.75,
        "film_hoop_median": 73.5,
        "n_tracks_used": 10,
        "n_tracks_total": 12,
        "ref_hoop_w": 98.0,
        "tracks_json": str(tracks_path),
    }
    (v6_dir / "film_scale.json").write_text(json.dumps(doc), encoding="utf-8")
    (d2_dir / "film_scale.json").write_text(json.dumps(doc), encoding="utf-8")
    out_dir = tmp_path / "vote_out"
    args = argparse.Namespace(
        tracks_json=tracks_path,
        v6_results=v6_results,
        d2v1_results=d2_results,
        out_dir=out_dir,
    )
    assert rfmm.cmd_vote(args) == 0
    rows = json.loads((out_dir / "make_miss.json").read_text(encoding="utf-8"))
    assert rows[0]["film_scale"] == 0.75
    assert rows[0]["film_hoop_median"] == 73.5
    assert rows[0]["n_tracks_used"] == 10
    summary = (out_dir / "summary.md").read_text(encoding="utf-8")
    assert "Film scale:" in summary
    assert "film_scale=0.75" in summary
    assert "film_hoop_median=73.5" in summary
    assert "n_tracks_used=10" in summary


def test_vote_errors_when_one_film_scale_missing(tmp_path):
    tracks_path, v6_results, d2_results, v6_dir, _d2_dir = _vote_scale_fixture(
        tmp_path
    )
    (v6_dir / "film_scale.json").write_text(
        json.dumps({"film_scale": 1.0, "film_hoop_median": 98.0, "n_tracks_used": 1}),
        encoding="utf-8",
    )
    args = argparse.Namespace(
        tracks_json=tracks_path,
        v6_results=v6_results,
        d2v1_results=d2_results,
        out_dir=tmp_path / "vote_one",
    )
    with pytest.raises(SystemExit, match="film_scale.json missing"):
        rfmm.cmd_vote(args)


def test_vote_errors_when_film_scale_mismatch(tmp_path):
    tracks_path, v6_results, d2_results, v6_dir, d2_dir = _vote_scale_fixture(
        tmp_path
    )
    (v6_dir / "film_scale.json").write_text(
        json.dumps({"film_scale": 1.0, "film_hoop_median": 98.0, "n_tracks_used": 1}),
        encoding="utf-8",
    )
    (d2_dir / "film_scale.json").write_text(
        json.dumps({"film_scale": 0.9, "film_hoop_median": 88.2, "n_tracks_used": 1}),
        encoding="utf-8",
    )
    args = argparse.Namespace(
        tracks_json=tracks_path,
        v6_results=v6_results,
        d2v1_results=d2_results,
        out_dir=tmp_path / "vote_mismatch",
    )
    with pytest.raises(SystemExit, match="differ"):
        rfmm.cmd_vote(args)


def test_vote_unchanged_when_neither_film_scale(tmp_path):
    tracks_path, v6_results, d2_results, _v6_dir, _d2_dir = _vote_scale_fixture(
        tmp_path
    )
    out_dir = tmp_path / "vote_neither"
    args = argparse.Namespace(
        tracks_json=tracks_path,
        v6_results=v6_results,
        d2v1_results=d2_results,
        out_dir=out_dir,
    )
    assert rfmm.cmd_vote(args) == 0
    rows = json.loads((out_dir / "make_miss.json").read_text(encoding="utf-8"))
    assert "film_scale" not in rows[0]
    assert "film_hoop_median" not in rows[0]
    assert "n_tracks_used" not in rows[0]
    summary = (out_dir / "summary.md").read_text(encoding="utf-8")
    assert "Film scale" not in summary


def test_module_source_scale_step_opens_no_labels_or_tags_path():
    src = (HERE / "rim_first_make_miss.py").read_text(encoding="utf-8")
    assert "film_tags" not in src
    assert "labels/" not in src
    assert "/tags/" not in src
    assert "\\tags\\" not in src
    assert "scoreboard_tracks" not in src
    assert "scoreboard_clock" not in src
    assert "data/scoreboard" not in src


# --- spec 46 scaled crop ---


class _FakeBox:
    def __init__(self, xyxy: Tuple[float, float, float, float], conf: float = 0.9):
        self.xyxy = [xyxy]
        self.conf = [conf]
        self.cls = [0]


class _FakePred:
    def __init__(self, boxes: Optional[List[_FakeBox]]):
        self.boxes = boxes


class _FakeModel:
    names = {0: "basketball"}

    def __init__(self, full_frame_centers: List[Tuple[float, float]]):
        # Centers in full-frame coords for successive successful frames.
        self._centers = list(full_frame_centers)
        self.crops: List[Tuple[int, int, int, int]] = []
        self._i = 0

    def predict(self, crop, conf=0.28, imgsz=640, verbose=False):
        # Infer crop origin from prior recorded call site via attached attrs.
        x0 = getattr(self, "_next_x0", 0)
        y0 = getattr(self, "_next_y0", 0)
        h, w = crop.shape[:2]
        self.crops.append((x0, y0, x0 + w, y0 + h))
        if self._i >= len(self._centers):
            return [_FakePred(None)]
        cx, cy = self._centers[self._i]
        self._i += 1
        # Box in crop coords so full-frame center is (cx, cy).
        a = cx - x0 - 5
        b = cy - y0 - 5
        c = cx - x0 + 5
        d = cy - y0 + 5
        return [_FakePred([_FakeBox((a, b, c, d))])]


class _FakeCap:
    def __init__(self, frame_h: int, frame_w: int, n_frames: int = 80):
        self._h = frame_h
        self._w = frame_w
        self._n = n_frames
        self._pos = 0
        self.set_calls: List[Any] = []

    def set(self, prop, value):
        self.set_calls.append((prop, value))
        self._pos = int(value)
        return True

    def read(self):
        if self._pos >= self._n:
            return False, None
        import numpy as np

        frame = np.zeros((self._h, self._w, 3), dtype=np.uint8)
        self._pos += 1
        return True, frame

    def get(self, _prop):
        return 25.0

    def release(self):
        return None


def _run_scaled_and_plain(
    centers: List[Tuple[float, float]],
    hoop: List[float],
    *,
    s: float,
    frame_h: int = 720,
    frame_w: int = 1280,
):
    """Drive v6_ball_scaled / v6_ball with the same centers; record crops."""
    row = {"t": 0}
    fps = 25.0

    class TrackingModel(_FakeModel):
        def predict(self, crop, conf=0.28, imgsz=640, verbose=False):
            # Caller slices frame[y0:y1, x0:x1]; recover bounds from shape + hoop math.
            return super().predict(crop, conf=conf, imgsz=imgsz, verbose=verbose)

    # Wrap so we know crop origin: patch by wrapping the function's slice via
    # a model that records the crop array's relationship. Instead, monkey the
    # predict to receive crop and compute x0/y0 from expected hoop expressions.
    hx, hy = hoop[0], hoop[1]

    class OriginModel(_FakeModel):
        def __init__(self, full_frame_centers, scale):
            super().__init__(full_frame_centers)
            self.scale = scale

        def predict(self, crop, conf=0.28, imgsz=640, verbose=False):
            # Reconstruct x0/y0 as v6_ball(_scaled) would have used.
            x0 = int(max(0, hx - 260 * self.scale))
            y0 = int(max(0, hy - 200 * self.scale))
            x1 = int(min(frame_w, hx + 260 * self.scale))
            y1 = int(min(frame_h, hy + 240 * self.scale))
            assert crop.shape[0] == y1 - y0
            assert crop.shape[1] == x1 - x0
            self._next_x0 = x0
            self._next_y0 = y0
            return super().predict(crop, conf=conf, imgsz=imgsz, verbose=verbose)

    model_s = OriginModel(centers, s)
    cap_s = _FakeCap(frame_h, frame_w, n_frames=len(centers) + 2)
    series_s = rfmm.v6_ball_scaled(model_s, cap_s, fps, row, hoop, s)

    model_p = OriginModel(centers, 1.0)
    cap_p = _FakeCap(frame_h, frame_w, n_frames=len(centers) + 2)
    series_p = q4.v6_ball(model_p, cap_p, fps, row, hoop)
    return series_s, series_p, model_s.crops, model_p.crops


def test_v6_ball_scaled_s1_equals_v6_ball():
    hoop = [400.0, 300.0, 98.0, 40.0]
    centers = [(410.0, 310.0), (405.0, 320.0), (400.0, 330.0)]
    series_s, series_p, crops_s, crops_p = _run_scaled_and_plain(
        centers, hoop, s=1.0
    )
    assert series_s == series_p
    assert crops_s == crops_p
    assert crops_s[0] == (
        int(max(0, 400.0 - 260)),
        int(max(0, 300.0 - 200)),
        int(min(1280, 400.0 + 260)),
        int(min(720, 300.0 + 240)),
    )


def test_v6_ball_scaled_crop_math_at_half():
    hoop = [400.0, 300.0, 64.0, 30.0]
    s = 0.5
    centers = [(400.0, 300.0)]
    series_s, _series_p, crops_s, _crops_p = _run_scaled_and_plain(
        centers, hoop, s=s
    )
    hx, hy = hoop[0], hoop[1]
    assert crops_s[0] == (
        int(max(0, hx - 260 * s)),
        int(max(0, hy - 200 * s)),
        int(min(1280, hx + 260 * s)),
        int(min(720, hy + 240 * s)),
    )
    assert series_s[0][1] == pytest.approx(400.0)
    assert series_s[0][2] == pytest.approx(300.0)


def test_crop_scale_doc_fields():
    info = {
        "film_scale": 0.658,
        "film_hoop_median": 64.5,
        "n_tracks_used": 31,
        "n_tracks_total": 31,
        "ref_hoop_w": 98.0,
    }
    doc = rfmm.crop_scale_doc(info)
    assert set(doc.keys()) == {
        "crop_scale",
        "film_hoop_median",
        "n_tracks_used",
        "n_tracks_total",
        "ref_hoop_w",
    }
    assert doc["crop_scale"] == 0.658
    assert doc["ref_hoop_w"] == 98.0
    assert "film_scale" not in doc


def test_find_reuse_source_by_t():
    source = [
        {"t": 1000, "moment_t_ms": 2000, "hoop": [1, 2, 3, 4], "ball": [], "bodd": []},
        {"t": 3000, "moment_t_ms": 4000, "hoop": [5, 6, 7, 8], "ball": [], "bodd": []},
    ]
    got = rfmm.find_reuse_source_track(source, start_ms=3000, moment_t_ms=9999)
    assert got["t"] == 3000


def test_find_reuse_source_by_moment_t_ms():
    source = [
        {
            "t": 1000,
            "moment_t_ms": 2000,
            "hoop": [1, 2, 98.0, 4],
            "ball": [(0, 1.0, 2.0)],
            "bodd": [(0, 1.0, 2.0)],
            "result": "make",
            "extra": "keep-me",
        }
    ]
    # start_ms does not match t; fall back to moment_t_ms
    got = rfmm.find_reuse_source_track(source, start_ms=999, moment_t_ms=2000)
    assert got["moment_t_ms"] == 2000
    assert got["extra"] == "keep-me"


def test_find_reuse_source_missing_exits():
    source = [{"t": 1, "moment_t_ms": 2, "hoop": [1, 2, 3, 4]}]
    with pytest.raises(SystemExit, match="no match"):
        rfmm.find_reuse_source_track(source, start_ms=99, moment_t_ms=88)


def test_cmd_tracks_reuse_drops_result_keeps_keys(tmp_path, monkeypatch):
    source_path = tmp_path / "src.json"
    source_path.write_text(
        json.dumps(
            [
                {
                    "t": 1000,
                    "moment_t_ms": 2000,
                    "hoop": [400.0, 300.0, 98.0, 40.0],
                    "ball": [(0, 9.0, 9.0)],
                    "bodd": [(0, 1.0, 2.0)],
                    "result": "make",
                    "extra": "kept",
                }
            ]
        ),
        encoding="utf-8",
    )
    tags = tmp_path / "tags.json"
    tags.write_text(json.dumps([2000]), encoding="utf-8")
    out_json = tmp_path / "out" / "tracks.json"
    video = tmp_path / "fake.mp4"
    video.write_text("x", encoding="utf-8")

    class _Y:
        def __init__(self, path):
            pass

    def _fill(tracks, *, video, s, v6_model):
        for row in tracks:
            row["ball"] = [(0, 1.0, 2.0)]

    monkeypatch.setattr("ultralytics.YOLO", _Y)
    monkeypatch.setattr(rfmm, "_fill_balls_scaled", _fill)
    # Avoid importing real collect path for V6 string only — YOLO mock is enough.
    import collect_q4_bodd as q4mod

    monkeypatch.setattr(q4mod, "V6", tmp_path / "v6.pt")

    args = argparse.Namespace(
        moments_json=None,
        tag_times_json=tags,
        video=video,
        out_json=out_json,
        lead_ms=1000,
        scaled_crop=True,
        reuse_hoops_from=source_path,
    )
    assert rfmm.cmd_tracks(args) == 0
    tracks = json.loads(out_json.read_text(encoding="utf-8"))
    assert len(tracks) == 1
    assert "result" not in tracks[0]
    assert tracks[0]["extra"] == "kept"
    assert tracks[0]["t"] == 1000
    assert tracks[0]["moment_t_ms"] == 2000
    assert tracks[0]["bodd"] == [[0, 1.0, 2.0]] or tracks[0]["bodd"] == [(0, 1.0, 2.0)]
    crop = json.loads((out_json.parent / "crop_scale.json").read_text(encoding="utf-8"))
    assert crop["crop_scale"] == 1.0
    assert crop["ref_hoop_w"] == 98.0
    assert set(crop.keys()) == {
        "crop_scale",
        "film_hoop_median",
        "n_tracks_used",
        "n_tracks_total",
        "ref_hoop_w",
    }


def test_cmd_tracks_reuse_missing_match_exits(tmp_path, monkeypatch):
    source_path = tmp_path / "src.json"
    source_path.write_text(
        json.dumps([{"t": 1, "moment_t_ms": 2, "hoop": [1, 2, 98.0, 4], "ball": []}]),
        encoding="utf-8",
    )
    tags = tmp_path / "tags.json"
    tags.write_text(json.dumps([9999]), encoding="utf-8")
    args = argparse.Namespace(
        moments_json=None,
        tag_times_json=tags,
        video=tmp_path / "v.mp4",
        out_json=tmp_path / "out.json",
        lead_ms=0,
        scaled_crop=True,
        reuse_hoops_from=source_path,
    )
    with pytest.raises(SystemExit, match="no match"):
        rfmm.cmd_tracks(args)


def test_cmd_tracks_flags_off_no_crop_scale(tmp_path, monkeypatch):
    tags = tmp_path / "tags.json"
    tags.write_text(json.dumps([1000]), encoding="utf-8")
    out_json = tmp_path / "tracks.json"
    video = tmp_path / "v.mp4"
    video.write_text("x", encoding="utf-8")

    class _Cap:
        def __init__(self, *_a, **_k):
            pass

        def get(self, _p):
            return 25.0

        def release(self):
            return None

    class _Y:
        def __init__(self, path):
            self.names = {0: "hoop", 1: "basketball"}

    calls = {"v6": 0, "scaled": 0}

    def fake_collect(model, cap, start):
        return [
            {
                "f": 0,
                "hoops": [{"x": 10.0, "y": 20.0, "w": 98.0, "h": 40.0, "c": 0.9}],
                "balls": [{"x": 11.0, "y": 21.0, "c": 0.9}],
            }
        ]

    def fake_groups(samples):
        return [(10.0, 20.0, 98.0, 40.0)]

    def fake_v6(model, cap, fps, row, hoop):
        calls["v6"] += 1
        return [(0, 1.0, 2.0)]

    def fake_scaled(*_a, **_k):
        calls["scaled"] += 1
        return [(0, 3.0, 4.0)]

    monkeypatch.setattr("cv2.VideoCapture", _Cap)
    monkeypatch.setattr("ultralytics.YOLO", _Y)
    import collect_q4_bodd as q4mod

    monkeypatch.setattr(q4mod, "collect_samples", fake_collect)
    monkeypatch.setattr(q4mod, "groups", fake_groups)
    monkeypatch.setattr(q4mod, "v6_ball", fake_v6)
    monkeypatch.setattr(q4mod, "BODD", tmp_path / "bodd.pt")
    monkeypatch.setattr(q4mod, "V6", tmp_path / "v6.pt")
    monkeypatch.setattr(rfmm, "v6_ball_scaled", fake_scaled)

    args = argparse.Namespace(
        moments_json=None,
        tag_times_json=tags,
        video=video,
        out_json=out_json,
        lead_ms=0,
        scaled_crop=False,
        reuse_hoops_from=None,
    )
    assert rfmm.cmd_tracks(args) == 0
    assert calls["v6"] == 1
    assert calls["scaled"] == 0
    assert not (tmp_path / "crop_scale.json").exists()
    tracks = json.loads(out_json.read_text(encoding="utf-8"))
    assert tracks[0]["ball"] == [[0, 1.0, 2.0]] or tracks[0]["ball"] == [(0, 1.0, 2.0)]


def test_cmd_d1_scaled_crop_requires_film_scale(tmp_path):
    args = _d1_args(tmp_path, film_scale=False, scaled_crop=True)
    with pytest.raises(SystemExit, match="requires --film-scale"):
        rfmm.cmd_d1(args)


def test_cmd_d1_crop_scale_json_mismatch_exits(tmp_path, monkeypatch):
    crop_path = tmp_path / "crop_scale.json"
    crop_path.write_text(json.dumps({"crop_scale": 0.5}), encoding="utf-8")
    monkeypatch.setattr(kbd, "main", _fake_main())
    args = _d1_args(
        tmp_path,
        film_scale=True,
        scaled_crop=True,
        crop_scale_json=crop_path,
    )
    # tracks have hoop width 3.0 -> scale 3/98 != 0.5
    with pytest.raises(SystemExit, match="crop_scale"):
        rfmm.cmd_d1(args)


def test_cmd_d1_scaled_crop_sets_and_restores_kbd(tmp_path, monkeypatch):
    tracks = [_hoop_track(1000, 98.0)]
    tracks_path = tmp_path / "tracks.json"
    tracks_path.write_text(json.dumps(tracks), encoding="utf-8")
    crop_path = tmp_path / "crop_scale.json"
    crop_path.write_text(json.dumps({"crop_scale": 1.0}), encoding="utf-8")

    before = (
        kbd.CROP_LEFT_RIGHT,
        kbd.CROP_ABOVE,
        kbd.CROP_BELOW,
        kbd.ZONE_BELOW_PX,
    )
    seen: dict = {}

    def _main(argv=None):
        argv = list(argv or [])
        step = argv[argv.index("--step") + 1]
        out_json = Path(argv[argv.index("--out-json") + 1])
        seen[step] = (
            kbd.CROP_LEFT_RIGHT,
            kbd.CROP_ABOVE,
            kbd.CROP_BELOW,
            kbd.ZONE_BELOW_PX,
        )
        if step == "extract":
            out_json.write_text("[]", encoding="utf-8")
            return 0
        out_json.write_text(json.dumps({"shots": []}), encoding="utf-8")
        return 0

    monkeypatch.setattr(kbd, "main", _main)
    args = _d1_args(
        tmp_path,
        film_scale=True,
        scaled_crop=True,
        crop_scale_json=crop_path,
        tracks_json=tracks_path,
    )
    assert rfmm.cmd_d1(args) == 0
    assert seen["extract"] == (260.0, 200.0, 240.0, 300.0)
    assert seen["arc-rule-report"] == (260.0, 200.0, 240.0, 300.0)
    assert (
        kbd.CROP_LEFT_RIGHT,
        kbd.CROP_ABOVE,
        kbd.CROP_BELOW,
        kbd.ZONE_BELOW_PX,
    ) == before
    film = json.loads((args.out_dir / "film_scale.json").read_text(encoding="utf-8"))
    assert film["kbd_crop"] == {
        "CROP_LEFT_RIGHT": 260.0,
        "CROP_ABOVE": 200.0,
        "CROP_BELOW": 240.0,
        "ZONE_BELOW_PX": 300.0,
    }


def test_cmd_d1_scaled_crop_restores_after_system_exit(tmp_path, monkeypatch):
    tracks = [_hoop_track(1000, 98.0)]
    tracks_path = tmp_path / "tracks.json"
    tracks_path.write_text(json.dumps(tracks), encoding="utf-8")
    before = (
        kbd.CROP_LEFT_RIGHT,
        kbd.CROP_ABOVE,
        kbd.CROP_BELOW,
        kbd.ZONE_BELOW_PX,
    )

    def report(out_json: Path) -> int:
        out_json.write_text(json.dumps({"shots": []}), encoding="utf-8")
        raise SystemExit("NO-OP PROOF FAILED detail")

    monkeypatch.setattr(kbd, "main", _fake_main(report=report))
    args = _d1_args(
        tmp_path,
        film_scale=True,
        scaled_crop=True,
        tracks_json=tracks_path,
    )
    with pytest.raises(SystemExit, match="NO-OP PROOF FAILED"):
        rfmm.cmd_d1(args)
    assert (
        kbd.CROP_LEFT_RIGHT,
        kbd.CROP_ABOVE,
        kbd.CROP_BELOW,
        kbd.ZONE_BELOW_PX,
    ) == before


def test_cmd_d1_flags_off_kbd_unchanged(tmp_path, monkeypatch):
    before = (
        kbd.CROP_LEFT_RIGHT,
        kbd.CROP_ABOVE,
        kbd.CROP_BELOW,
        kbd.ZONE_BELOW_PX,
    )
    monkeypatch.setattr(kbd, "main", _fake_main())
    args = _d1_args(tmp_path, film_scale=False, scaled_crop=False)
    assert rfmm.cmd_d1(args) == 0
    assert (
        kbd.CROP_LEFT_RIGHT,
        kbd.CROP_ABOVE,
        kbd.CROP_BELOW,
        kbd.ZONE_BELOW_PX,
    ) == before
    assert not (args.out_dir / "film_scale.json").exists()
    film_path = args.out_dir / "film_scale.json"
    assert not film_path.exists()
