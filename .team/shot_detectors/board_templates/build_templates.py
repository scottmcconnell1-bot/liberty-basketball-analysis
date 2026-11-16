"""Build home.npz and away_adrian.npz once from design48b labels + seen films.

Usage (Windows, Claude Code):
  python .team/shot_detectors/board_templates/build_templates.py --videos-dir PATH

Does not invent thresholds: board box from game_session.find_board; digit train
matches knn48.train / adrian_read48.train; ref/max_dist per spec 48b S1.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
DET = HERE.parent
DESIGN = DET.parent / "design48b"
sys.path.insert(0, str(DET))
import game_session as gs  # noqa: E402

FILM_FILES = {
    "adrian": "nfhs_gam0a66d85e12.mp4",
    "notus": "LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4",
    "gv": "LIBERTY_H_v_GARDEN_VALLEY_A_20260809_221334.mp4",
    "idaho": "LIBERTY_H_v_IDAHO_CITY_A_20260809_221334.mp4",
}
HOME_FILMS = ("notus", "gv", "idaho")
AWAY_FILMS = ("adrian",)


def _video_path(videos_dir: Path, film: str) -> Path:
    path = videos_dir / FILM_FILES[film]
    if not path.is_file():
        raise SystemExit(f"missing video: {path}")
    return path


def _boxes_for_films(videos_dir: Path, films: tuple[str, ...]) -> dict[str, list[int]]:
    boxes: dict[str, list[int]] = {}
    for film in films:
        boxes[film] = gs.find_board(_video_path(videos_dir, film))
        print(film, "box", boxes[film])
    return boxes


def _board_images(
    videos_dir: Path, meta: list[dict], films: tuple[str, ...], boxes: dict[str, list[int]]
) -> list[np.ndarray]:
    caps: dict[str, cv2.VideoCapture] = {}
    imgs: list[np.ndarray] = []
    for m in meta:
        film = m["film"]
        if film not in films:
            continue
        if film not in caps:
            caps[film] = cv2.VideoCapture(str(_video_path(videos_dir, film)))
        cap = caps[film]
        cap.set(cv2.CAP_PROP_POS_MSEC, m["t_ms"])
        ok, fr = cap.read()
        if not ok or fr is None:
            continue
        imgs.append(gs._board_image(fr, boxes[film]))
    for cap in caps.values():
        cap.release()
    if not imgs:
        raise SystemExit(f"no board images for {films}")
    return imgs


def _ref_and_max_dist(imgs: list[np.ndarray]) -> tuple[np.ndarray, float]:
    ref = np.mean(np.stack(imgs), axis=0).astype(np.float32)
    max_dist = float(max(np.mean(np.abs(im - ref)) for im in imgs))
    return ref, max_dist


def train_home(videos_dir: Path, boxes: dict[str, list[int]]) -> tuple[np.ndarray, np.ndarray]:
    """Port of knn48.train: skip frames whose digit-blob count differs from the label."""
    meta = json.loads((DESIGN / "train48_meta.json").read_text(encoding="utf-8"))
    labels = json.loads((DESIGN / "labels48_train_home.json").read_text(encoding="utf-8"))
    caps: dict[str, cv2.VideoCapture] = {}
    X: list[np.ndarray] = []
    y: list[str] = []
    skipped: list[str] = []
    for k, lab in labels.items():
        m = meta[int(k)]
        f = m["film"]
        if f not in HOME_FILMS:
            continue
        if f not in caps:
            caps[f] = cv2.VideoCapture(str(_video_path(videos_dir, f)))
        cap = caps[f]
        cap.set(cv2.CAP_PROP_POS_MSEC, m["t_ms"])
        ok, fr = cap.read()
        if not ok or fr is None:
            skipped.append(k)
            continue
        c = gs.clock_crop(fr, boxes[f], "home")
        bl, mk = gs.blobs(c)
        digs = [b for b in bl if b[4] == "d"]
        chars = [ch for ch in lab if ch.isdigit()]
        if len(digs) != len(chars):
            skipped.append(k)
            continue
        for b, ch in zip(digs, chars):
            X.append(gs.digit_vec(mk, b))
            y.append(ch)
    for cap in caps.values():
        cap.release()
    print("home train skipped", skipped)
    return np.asarray(X, dtype=np.float32), np.asarray(y)


def train_adrian(videos_dir: Path, boxes: dict[str, list[int]]) -> tuple[np.ndarray, np.ndarray]:
    """Port of adrian_read48.train."""
    meta = json.loads((DESIGN / "train48_meta.json").read_text(encoding="utf-8"))
    lab = json.loads((DESIGN / "labels48_train_adrian.json").read_text(encoding="utf-8"))
    cap = cv2.VideoCapture(str(_video_path(videos_dir, "adrian")))
    X: list[np.ndarray] = []
    y: list[str] = []
    for k, v in lab.items():
        cap.set(cv2.CAP_PROP_POS_MSEC, meta[int(k)]["t_ms"])
        ok, fr = cap.read()
        if not ok or fr is None:
            continue
        cv = gs._cell_vecs(gs.clock_crop(fr, boxes["adrian"], "away_adrian"))
        if v.startswith("."):
            X.append(cv[2][1])
            y.append(v[1])
        else:
            X.append(cv[2][1])
            y.append(v[0])
            X.append(cv[3][1])
            y.append(v[1])
    cap.release()
    return np.asarray(X, dtype=np.float32), np.asarray(y)


def _write_npz(
    path: Path, X: np.ndarray, y: np.ndarray, ref: np.ndarray, max_dist: float
) -> str:
    np.savez(
        path,
        X=X.astype(np.float32),
        y=np.asarray(y),
        ref=ref.astype(np.float32),
        max_dist=np.float32(max_dist),
    )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    print(path.name, "sha256", digest, "X", X.shape, "max_dist", max_dist)
    return digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="build_templates")
    parser.add_argument("--videos-dir", required=True)
    args = parser.parse_args(argv)
    videos_dir = Path(args.videos_dir)
    meta = json.loads((DESIGN / "train48_meta.json").read_text(encoding="utf-8"))

    home_boxes = _boxes_for_films(videos_dir, HOME_FILMS)
    home_imgs = _board_images(videos_dir, meta, HOME_FILMS, home_boxes)
    home_ref, home_max = _ref_and_max_dist(home_imgs)
    home_X, home_y = train_home(videos_dir, home_boxes)
    home_sha = _write_npz(HERE / "home.npz", home_X, home_y, home_ref, home_max)

    away_boxes = _boxes_for_films(videos_dir, AWAY_FILMS)
    away_imgs = _board_images(videos_dir, meta, AWAY_FILMS, away_boxes)
    away_ref, away_max = _ref_and_max_dist(away_imgs)
    away_X, away_y = train_adrian(videos_dir, away_boxes)
    away_sha = _write_npz(
        HERE / "away_adrian.npz", away_X, away_y, away_ref, away_max
    )

    readme = HERE / "README.md"
    text = readme.read_text(encoding="utf-8") if readme.is_file() else ""
    lines = [
        "# Board templates",
        "",
        "Built by `build_templates.py --videos-dir PATH` from `.team/design48b/` labels",
        "and `train48_meta.json`. Board box from `game_session.find_board`.",
        "",
        "npz keys:",
        "- `X` float32 (N, 240) digit vectors",
        "- `y` str (N,) digit labels",
        "- `ref` float32 (72, 128) reference board image",
        "- `max_dist` float scalar",
        "",
        "sha256 (filled by build_templates.py):",
        f"- home.npz: `{home_sha}`",
        f"- away_adrian.npz: `{away_sha}`",
        "",
    ]
    if "sha256" in text and "pending" not in text.lower():
        # still rewrite with fresh digests after each build
        pass
    readme.write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
