"""Train kNN digit templates from hand-marked seen frames; read a clock string from a crop."""
import sys, json
sys.path.insert(0, r"C:/Users/scott/AppData/Local/Temp/claude/9519414f725d5b3e/1ad6458c-fdef-4ea9-acfc-295e30fb4711/scratchpad")
from digits48 import *
import numpy as np


def sep_char(m, b):
    x0, x1, y0, y1, _ = b
    cy = (y0 + y1) / 2
    return "." if cy > 0.6 * SCALE_H and (y1 - y0) < 0.3 * SCALE_H else ":"


def train(board, labels):
    meta = json.load(open(f"{S}/train48_meta.json"))
    X, y, skipped = [], [], []
    caps = {}
    for k, lab in labels.items():
        m = meta[int(k)]
        f = m["film"]
        if f not in caps:
            caps[f] = cv2.VideoCapture(U + FILMS[f][0])
        cap = caps[f]
        cap.set(cv2.CAP_PROP_POS_MSEC, m["t_ms"]); ok, fr = cap.read()
        c = clock_crop(fr, f); bl, mk = blobs(c)
        digs = [b for b in bl if b[4] == "d"]
        chars = [ch for ch in lab if ch.isdigit()]
        if len(digs) != len(chars):
            skipped.append(k); continue
        for b, ch in zip(digs, chars):
            X.append(digit_vec(mk, b)); y.append(ch)
    return np.array(X), np.array(y), skipped


def read(crop, X, y):
    bl, mk = blobs(crop)
    s = ""
    for b in bl:
        if b[4] == "d":
            v = digit_vec(mk, b)
            s += y[np.argmin(((X - v) ** 2).sum(axis=1))]
        else:
            s += sep_char(mk, b)
    return s
