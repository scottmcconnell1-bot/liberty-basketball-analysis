"""D2 dataset build (spec .team/specs/23_d2_train_job_spec.md v2, section 2).

Turns Scott's kept labels (labels_live.json, 514 crops) into a YOLO dataset outside the repo:
  <out>/images/{train,val}/<crop>.jpg, <out>/labels/{train,val}/<crop>.txt, data.yaml, split.json.
Box [x, y, w, h] (top-left, crop pixels) -> "0 xc yc w h" normalized by that crop's real size.
No-ball crop -> empty label file (background). Val split by window, about 15% of windows per
film, seed 42; train and val never share a window. Refuses a non-empty output folder.

Usage: python d2_build_dataset.py <labels_live.json> <d2_frames dir> <out ds dir>
"""
import json
import os
import random
import shutil
import sys

FILMS = [
    "LIBERTY_A_v_HSB_H1_20260809_221334",
    "LIBERTY_A_v_HSB_H_20260809_221334",
    "LIBERTY_A_v_RIMROCK_H_20260809_221334",
    "LIBERTY_H_v_GARDEN_VALLEY_A_20260809_221334",
    "LIBERTY_H_v_IDAHO_CITY_A_20260809_221334",
    "LIBERTY_H_v_RIVERSTONE_A_20260809_221334",
    "LIBERTY_H_v_NOTUS_A_20260809_221334",
]
WINDOW_GAP = 40      # spec 23 section 2: a crop within 40 frames of the previous one is the same window
VAL_FRACTION = 0.15
SEED = 42


def parse_name(name):
    """'<film stem>_frNNNNNN.jpg' -> (film stem, frame number). Refuses a film not in the 7."""
    if not name.endswith(".jpg") or "_fr" not in name:
        raise ValueError("not a crop name: " + name)
    stem, num = name[:-4].rsplit("_fr", 1)
    if stem not in FILMS:
        raise ValueError("crop from a film not in the 7: " + name)
    return stem, int(num)


def to_yolo(box, width, height):
    x, y, w, h = box
    if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > width or y + h > height:
        raise ValueError("box outside crop: %r in %dx%d" % (box, width, height))
    return "0 %.6f %.6f %.6f %.6f" % ((x + w / 2) / width, (y + h / 2) / height, w / width, h / height)


def windows(names):
    """{crop name: window id}. Within a film, sorted by frame, a gap > 40 starts a new window."""
    by_film = {}
    for n in names:
        film, fn = parse_name(n)
        by_film.setdefault(film, []).append((fn, n))
    out = {}
    for film in FILMS:
        rows = sorted(by_film.get(film, []))
        k, prev = -1, None
        for fn, n in rows:
            if prev is None or fn - prev > WINDOW_GAP:
                k += 1
            out[n] = "%s_w%03d" % (film, k)
            prev = fn
    return out


def split(win):
    """{crop name: 'train' | 'val'}; about 15% of each film's windows go to val, seed 42."""
    rng = random.Random(SEED)
    val = set()
    for film in FILMS:
        ids = sorted({w for w in win.values() if w.startswith(film + "_w")})
        if not ids:
            continue
        n_val = max(1, round(VAL_FRACTION * len(ids)))
        val.update(rng.sample(ids, n_val))
    return {n: ("val" if w in val else "train") for n, w in win.items()}


def image_size(path):
    import cv2
    img = cv2.imread(path)
    if img is None:
        raise ValueError("cannot read image: " + path)
    return img.shape[1], img.shape[0]


def build(labels_path, frames_dir, out_dir, size_of=image_size):
    if os.path.isdir(out_dir) and os.listdir(out_dir):
        raise SystemExit("STOP: output folder is not empty: " + out_dir)
    rows = json.load(open(labels_path, encoding="utf-8"))
    names = [r["frame"] for r in rows]
    if len(set(names)) != len(names):
        raise SystemExit("STOP: a crop is labelled twice")
    for n in names:
        parse_name(n)
    win = windows(names)
    sp = split(win)
    for part in ("train", "val"):
        os.makedirs(os.path.join(out_dir, "images", part))
        os.makedirs(os.path.join(out_dir, "labels", part))
    counts = {"train": [0, 0], "val": [0, 0]}
    for r in rows:
        n, part = r["frame"], sp[r["frame"]]
        src = os.path.join(frames_dir, n)
        w, h = size_of(src)
        lines = [to_yolo(b, w, h) for b in r["boxes"]]
        shutil.copyfile(src, os.path.join(out_dir, "images", part, n))
        with open(os.path.join(out_dir, "labels", part, n[:-4] + ".txt"), "w") as f:
            f.write("\n".join(lines) + ("\n" if lines else ""))
        counts[part][0 if lines else 1] += 1
    root = os.path.abspath(out_dir).replace("\\", "/")
    with open(os.path.join(out_dir, "data.yaml"), "w") as f:
        f.write("path: %s\ntrain: images/train\nval: images/val\nnames:\n  0: basketball\n" % root)
    with open(os.path.join(out_dir, "split.json"), "w") as f:
        json.dump({"seed": SEED, "window_gap": WINDOW_GAP, "val_fraction": VAL_FRACTION,
                   "counts": {p: {"ball": c[0], "no_ball": c[1]} for p, c in counts.items()},
                   "frames": {n: {"split": sp[n], "window": win[n]} for n in sorted(names)}}, f, indent=1)
    return counts


if __name__ == "__main__":
    c = build(sys.argv[1], sys.argv[2], sys.argv[3])
    print("train ball %d no-ball %d | val ball %d no-ball %d" % (c["train"][0], c["train"][1], c["val"][0], c["val"][1]))
