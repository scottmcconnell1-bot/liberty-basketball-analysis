"""Option 2 prototype: segment clock crop into blobs (digits / separators). Seen films only."""
import random
import cv2, numpy as np
REPO = r"C:/Users/scott/Documents/liberty-basketball-analysis"
U = REPO + "/uploads/"
S = r"C:/Users/scott/AppData/Local/Temp/claude/9519414f725d5b3e/1ad6458c-fdef-4ea9-acfc-295e30fb4711/scratchpad"
HOME = ((1012, 560, 242, 135), (0.20, 0.80, 0.0, 0.30))
FILMS = {"adrian": ("nfhs_gam0a66d85e12.mp4", (1517, 840, 365, 205), (0.12, 0.72, 0.0, 0.30)),
         "notus": ("LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4",) + HOME,
         "gv": ("LIBERTY_H_v_GARDEN_VALLEY_A_20260809_221334.mp4",) + HOME,
         "idaho": ("LIBERTY_H_v_IDAHO_CITY_A_20260809_221334.mp4",) + HOME}
BOARD = {"adrian": "away_adrian", "notus": "home", "gv": "home", "idaho": "home"}
SCALE_H = 96  # normalise crop height


def clock_crop(frame, film):
    _, (x, y, w, h), (a, b, c, d) = FILMS[film]
    crop = frame[y + int(c * h): y + int(d * h), x + int(a * w): x + int(b * w)]
    return cv2.resize(crop, (int(crop.shape[1] * SCALE_H / crop.shape[0]), SCALE_H), interpolation=cv2.INTER_CUBIC)


def lit_mask(crop):
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    m = ((hsv[..., 2] > 120) & (hsv[..., 1] > 90) & (hsv[..., 0] >= 5) & (hsv[..., 0] <= 40)).astype(np.uint8)
    return cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))


def blobs(crop):
    """Return list of (x0, x1, y0, y1, kind) left to right; kind 'd' digit or 's' separator."""
    m = lit_mask(crop)
    col = m.sum(axis=0) > 0
    runs, i, W = [], 0, len(col)
    while i < W:
        if col[i]:
            j = i
            while j < W and col[j]:
                j += 1
            runs.append([i, j]); i = j
        else:
            i += 1
    merged = []
    for r in runs:  # merge runs split by tiny gaps (dot-matrix LEDs)
        if merged and r[0] - merged[-1][1] <= 3:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    out = []
    for x0, x1 in merged:
        rows = np.where(m[:, x0:x1].sum(axis=1) > 0)[0]
        if len(rows) == 0:
            continue
        y0, y1 = rows[0], rows[-1] + 1
        if (x1 - x0) * (y1 - y0) < 20:
            continue
        lit_rows = (m[y0:y1, x0:x1].sum(axis=1) > 0).mean()
        kind = "d" if (y1 - y0) >= 0.45 * SCALE_H and lit_rows >= 0.6 else "s"
        out.append((x0, x1, y0, y1, kind))
    return out, m


def digit_vec(m, b):
    x0, x1, y0, y1, _ = b
    g = m[y0:y1, x0:x1].astype(np.float32)
    # keep aspect: pad to fixed width ratio so a '1' stays thin
    h, w = g.shape
    W = max(w, int(h * 0.62))
    pad = np.zeros((h, W), np.float32); pad[:, W - w:] = g  # right-align (7-seg '1' sits right)
    return cv2.resize(pad, (12, 20), interpolation=cv2.INTER_AREA).ravel()


def sample_frames(film, n, seed, exclude=()):
    fn = FILMS[film][0]
    cap = cv2.VideoCapture(U + fn)
    N = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); fps = cap.get(cv2.CAP_PROP_FPS)
    rng = random.Random(seed)
    idx = []
    while len(idx) < n:
        i = rng.randrange(N)
        if all(abs(i - e) > fps * 5 for e in list(exclude) + idx):
            idx.append(i)
    out = []
    for i in sorted(idx):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i); ok, f = cap.read()
        if ok:
            out.append((int(i / fps * 1000), f))
    return out


def sheet(items, path, cols=4):
    """items: list of (crop, blobs, caption)."""
    tiles = []
    for crop, bl, cap in items:
        t = crop.copy()
        for k, (x0, x1, y0, y1, kind) in enumerate(bl):
            cv2.rectangle(t, (x0, y0), (x1 - 1, y1 - 1), (0, 255, 0) if kind == "d" else (255, 0, 255), 1)
        t = cv2.resize(t, (300, int(300 * t.shape[0] / t.shape[1])))
        lab = np.zeros((26, 300, 3), np.uint8)
        cv2.putText(lab, cap, (3, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
        tiles.append(cv2.vconcat([t, lab]))
    H = max(t.shape[0] for t in tiles)
    tiles = [cv2.copyMakeBorder(t, 0, H - t.shape[0], 0, 4, cv2.BORDER_CONSTANT) for t in tiles]
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    cv2.imwrite(path, cv2.vconcat([cv2.hconcat(tiles[r:r + cols]) for r in range(0, len(tiles), cols)]))
