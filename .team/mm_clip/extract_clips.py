"""Make/miss clip model - step 1: extract hoop-centred clips for every finder moment of a film.

Default window (clips7 / clips7a): 32 frames at t = trigger - 0.88 s .. + 1.60 s (0.08 s step).
Spec 52d window (--window 52d): 44 frames at t = trigger - 0.88 s .. + 6.0 s (0.16 s step).
Crop centred on the finder's hoop (x, y = hoop centre), width 2.6 x hoop width, height 3.0 x hoop
width (1.2 hw above the rim centre, 1.8 hw below), resized to 96 x 112 (w x h), BGR uint8.
Labels: 0 = not a shot, 1 = miss, 2 = make, -1 = unknown / excluded.

Usage: python extract_clips.py <film_id> <moments.json> <video> <labels source> <out.npz> [--window NAME]
labels source:  'gvfmt:<labels.json>'  (specs/44_gv_labels.json format: shot/result per t_ms)
                'labels52a:<labels.json>'  (review52/labels52a_class0_restore.json: films[film].t_ms/y)
                'tags|<labels_film.json>|<tags.json>'  (spec-47 frozen labels rows + coach tags file)
                'none'  (unlabelled film: all -1)
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / ".team/shot_detectors"))

# Default = clips7 / clips7a geometry (unchanged). Select 52d via --window 52d.
WINDOWS = {
    "clips7": dict(T0=-0.88, STEP=0.08, WINDOW_END_S=1.60, N=32),
    "52d": dict(T0=-0.88, STEP=0.16, WINDOW_END_S=6.0, N=44),
}

T0, STEP, WINDOW_END_S, N = (
    WINDOWS["clips7"]["T0"],
    WINDOWS["clips7"]["STEP"],
    WINDOWS["clips7"]["WINDOW_END_S"],
    WINDOWS["clips7"]["N"],
)
K_TRIG = int(round(-T0 / STEP))  # clips7: 11; 52d: 6
OUT_W, OUT_H = 96, 112
UP, DOWN, HALF_W = 1.2, 1.8, 1.3


def set_window(name):
    """Apply a named window pin; updates module-level T0/STEP/WINDOW_END_S/N/K_TRIG."""
    global T0, STEP, WINDOW_END_S, N, K_TRIG
    if name not in WINDOWS:
        raise SystemExit(f"unknown --window {name!r}; choose from {sorted(WINDOWS)}")
    w = WINDOWS[name]
    T0, STEP, WINDOW_END_S, N = w["T0"], w["STEP"], w["WINDOW_END_S"], w["N"]
    # Derive N from end if the pin supplies WINDOW_END_S (assert matches pinned N).
    n_derived = int(round((WINDOW_END_S - T0) / STEP)) + 1
    if n_derived != N:
        raise SystemExit(f"window {name}: N pin {N} != derived {n_derived}")
    K_TRIG = int(round(-T0 / STEP))
    return T0, STEP, WINDOW_END_S, N, K_TRIG


def labels_gvfmt(path, moments):
    lab = json.load(open(path))["moments"]
    out = []
    for m in moments:
        v = lab.get(str(m["t_ms"]))
        if v is None:
            out.append(-1)
        elif v.get("shot") == "no":
            out.append(0)
        elif v.get("shot") == "yes" and v.get("result") == "miss":
            out.append(1)
        elif v.get("shot") == "yes" and v.get("result") == "make":
            out.append(2)
        else:
            out.append(-1)
    return out


def labels_labels52a(path, moments, film):
    """labels52a_class0_restore.json: films[film].t_ms / .y parallel arrays -> per-moment y."""
    films = json.load(open(path))["films"]
    if film not in films:
        raise SystemExit(f"labels52a has no film {film!r}")
    row = films[film]
    by_t = {int(t): int(y) for t, y in zip(row["t_ms"], row["y"])}
    return [by_t.get(int(m["t_ms"]), -1) for m in moments]


def labels_tags(rows_path, tags_path, moments):
    import find_shots_measure as fsm
    rows = {r["moment_t_ms"]: r for r in json.load(open(rows_path))["rows"]}
    tags = {t["t"]: t for t in fsm.load_shot_tags(Path(tags_path))}
    out = []
    for m in moments:
        r = rows.get(m["t_ms"])
        if r is None or r.get("excluded_reason"):
            out.append(-1)
            continue
        tt = r.get("matched_tag_t_ms")
        if tt is not None:
            res = str(tags[tt].get("result") or tags[tt].get("eventresult") or "").lower()
            out.append(2 if res.startswith("make") else 1 if res.startswith("miss") else -1)
        else:
            # R1: unmatched -> -1 always (near-tag duplicate or far-from-tag unknown); never auto 0
            out.append(-1)
    return out


def track_hoop(frames, cx, cy, hw, W, H):
    """Follow the hoop through a panning camera: template = backboard + rim around the finder's hoop in the
    trigger frame (x +-1.1 hw, y -1.3..+0.5 hw), matched (normalised cross-correlation, grayscale) in each
    neighbouring frame within +-1.2 hw of the previous position, outward from the trigger frame.
    A weak match (< 0.45) keeps the previous position."""
    cen = [(cx, cy)] * len(frames)
    ref = frames[K_TRIG] if frames[K_TRIG] is not None else next((f for f in frames if f is not None), None)
    if ref is None:
        return cen
    g = lambda fr: cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
    tx0, tx1 = int(max(0, cx - 1.1 * hw)), int(min(W, cx + 1.1 * hw))
    ty0, ty1 = int(max(0, cy - 1.3 * hw)), int(min(H, cy + 0.5 * hw))
    if tx1 - tx0 < 8 or ty1 - ty0 < 8:
        return cen
    tmpl = g(ref)[ty0:ty1, tx0:tx1]
    offx, offy = cx - tx0, cy - ty0  # hoop centre inside the template
    for order in (range(K_TRIG + 1, len(frames)), range(K_TRIG - 1, -1, -1)):
        px, py = cx, cy
        for k in order:
            fr = frames[k]
            if fr is None:
                cen[k] = (px, py); continue
            m = 1.2 * hw
            sx0, sy0 = int(max(0, px - offx - m)), int(max(0, py - offy - m))
            sx1, sy1 = int(min(W, px - offx + tmpl.shape[1] + m)), int(min(H, py - offy + tmpl.shape[0] + m))
            win = g(fr)[sy0:sy1, sx0:sx1]
            if win.shape[0] >= tmpl.shape[0] and win.shape[1] >= tmpl.shape[1]:
                res = cv2.matchTemplate(win, tmpl, cv2.TM_CCOEFF_NORMED)
                _, mx, _, loc = cv2.minMaxLoc(res)
                if mx >= 0.45:
                    px, py = sx0 + loc[0] + offx, sy0 + loc[1] + offy
            cen[k] = (px, py)
    return cen


def rim_offset(frame, cx, cy, hw):
    """Offset from the finder's hoop point to the rim itself: red/orange mask (H<=15 or >=165, S>90, V>70) in
    x +-1.2 hw, y -1.2..+0.8 hw; the rim = the widest flat component (w >= 0.35 hw, w/h >= 1.8) nearest the
    point. Returns (dx, dy) or (0, 0) if none."""
    if frame is None:
        return 0.0, 0.0
    H, W = frame.shape[:2]
    x0, x1 = int(max(0, cx - 1.2 * hw)), int(min(W, cx + 1.2 * hw))
    y0, y1 = int(max(0, cy - 1.2 * hw)), int(min(H, cy + 0.8 * hw))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return 0.0, 0.0
    hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    hh, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    m = (((hh <= 15) | (hh >= 165)) & (s > 90) & (v > 70)).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 5), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    best, bd = None, 1e9
    for j in range(1, n):
        bx, by, bw, bh, area = st[j]
        if bw >= 0.35 * hw and bw >= 1.8 * max(bh, 1):
            rx, ry = x0 + bx + bw / 2, y0 + by + bh / 2
            d = (rx - cx) ** 2 + (ry - cy) ** 2
            if d < bd:
                best, bd = (rx - cx, ry - cy), d
    return best if best is not None else (0.0, 0.0)


def labels_tagmatch(tags_path, moments, window_ms=4000):
    """Candidates labelled straight from coach tags: greedy nearest match within window -> tag result;
    unmatched -> -1 always (near-tag duplicate or far-from-tag unknown); never auto 0 (R1)."""
    import find_shots_measure as fsm
    tags = fsm.load_shot_tags(Path(tags_path))
    tt = [t["t"] for t in tags]
    mt = [m["t_ms"] for m in moments]
    r = fsm.match_shot_indices(tt, mt, window_ms)
    out = [None] * len(moments)
    for ti, fi, _ in r["matches"]:
        res = str(tags[ti].get("result") or "").lower()
        out[fi] = 2 if res.startswith("make") else 1 if res.startswith("miss") else -1
    for fi in r["unmatched_finder"]:
        out[fi] = -1
    return out


def labels_inherit(gvfmt_path, labelled_moments_path, moments, tol_ms=1000):
    """Candidates labelled from an already-labelled moment list (gv format) when within tol_ms; else -1."""
    lab = labels_gvfmt(gvfmt_path, json.load(open(labelled_moments_path))["moments"])
    ref = [(m["t_ms"], y) for m, y in zip(json.load(open(labelled_moments_path))["moments"], lab)]
    out = []
    for m in moments:
        best = min(ref, key=lambda r: abs(r[0] - m["t_ms"]))
        out.append(best[1] if abs(best[0] - m["t_ms"]) <= tol_ms else -1)
    return out


def extract(moments, video):
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS)
    W, H = int(cap.get(3)), int(cap.get(4))
    clips = np.zeros((len(moments), N, OUT_H, OUT_W, 3), np.uint8)
    for i, m in enumerate(moments):
        h = m.get("hoop") or {}
        cx, cy, hw = float(h.get("x", W / 2)), float(h.get("y", H / 3)), float(h.get("w", 60))
        t_trig = m["t_ms"] / 1000.0
        want = [int(round((t_trig + T0 + k * STEP) * fps)) for k in range(N)]
        f_start = max(0, want[0])
        cap.set(cv2.CAP_PROP_POS_FRAMES, f_start)
        f = f_start
        frame = None
        frames = [None] * N
        for k, wf in enumerate(want):
            wf = max(0, wf)
            while f <= wf:
                ok, fr = cap.read()
                if not ok:
                    break
                frame, f = fr, f + 1
            frames[k] = frame
        centres = track_hoop(frames, cx, cy, hw, W, H)
        dx, dy = rim_offset(frames[K_TRIG], cx, cy, hw)
        centres = [(x + dx, y + dy) for x, y in centres]
        for k in range(N):
            if frames[k] is None:
                continue
            tx, ty = centres[k]
            x0, x1 = int(round(tx - HALF_W * hw)), int(round(tx + HALF_W * hw))
            y0, y1 = int(round(ty - UP * hw)), int(round(ty + DOWN * hw))
            fr = frames[k]
            pad = cv2.copyMakeBorder(fr, max(0, -y0), max(0, y1 - H), max(0, -x0), max(0, x1 - W), cv2.BORDER_CONSTANT)
            ox, oy = max(0, -x0), max(0, -y0)
            crop = pad[y0 + oy:y1 + oy, x0 + ox:x1 + ox]
            clips[i, k] = cv2.resize(crop, (OUT_W, OUT_H), interpolation=cv2.INTER_AREA)
        if i % 50 == 0:
            print(f"  {i}/{len(moments)}", flush=True)
    return clips


def main(argv=None):
    ap = argparse.ArgumentParser(description="Extract hoop-centred make/miss clips")
    ap.add_argument("film")
    ap.add_argument("moments_json")
    ap.add_argument("video")
    ap.add_argument("labels_source")
    ap.add_argument("out_npz")
    ap.add_argument(
        "--window",
        default="clips7",
        choices=sorted(WINDOWS),
        help="clip window pin (default clips7 = clips7/clips7a geometry; 52d = longer post-shot)",
    )
    a = ap.parse_args(argv)
    set_window(a.window)
    film, mj, video, src, out = a.film, a.moments_json, a.video, a.labels_source, a.out_npz
    d = json.load(open(mj))
    moments = d["moments"]
    if src == "none":
        y = [-1] * len(moments)
    elif src.startswith("gvfmt:"):
        y = labels_gvfmt(src[6:], moments)
    elif src.startswith("labels52a:"):
        y = labels_labels52a(src.split(":", 1)[1], moments, film)
    elif src.startswith("tagmatch|"):
        y = labels_tagmatch(src.split("|", 1)[1], moments)
    elif src.startswith("inherit|"):
        _, g, lm = src.split("|", 2)
        y = labels_inherit(g, lm, moments)
    elif src.startswith("tags|"):
        _, rows, tags = src.split("|", 2)
        y = labels_tags(rows, tags, moments)
    else:
        raise SystemExit("bad labels source")
    clips = extract(moments, video)
    hw = np.array([float((m.get("hoop") or {}).get("w", 0)) for m in moments], np.float32)
    np.savez_compressed(
        out,
        clips=clips,
        y=np.array(y, np.int8),
        t_ms=np.array([m["t_ms"] for m in moments], np.int64),
        hoop_w=hw,
        film=np.array(film),
    )
    vals, cnt = np.unique(y, return_counts=True)
    print(
        film,
        "window", a.window,
        f"N={N} K_TRIG={K_TRIG} STEP={STEP}",
        "moments", len(moments),
        "labels", dict(zip(vals.tolist(), cnt.tolist())),
        "->", out,
    )


if __name__ == "__main__":
    main()
