"""Game session from the scoreboard clock only (spec 48b).

Reads the clock crop only. Never reads score. applied_to_core stays false.
A make is still ball_through_rim or net_moved_after_shot.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
TEMPLATES_DIR = HERE / "board_templates"

# --- fixed numbers from spec 48b S1-S9 / S7b / design48b — do not add others ---
BOARD_PROBE_N = 30
BOARD_DARK_GRAY = 45
BOARD_DARK_FRAC = 0.85
BOARD_CLOSE = 9
BOARD_REF_W, BOARD_REF_H = 128, 72
BOARD_NEW_MULT = 1.5
SCALE_H = 96
HOME_CROP = (0.20, 0.80, 0.0, 0.30)
AWAY_CROP = (0.24, 0.80, 0.0, 0.28)
HOME_V, HOME_S, HOME_H0, HOME_H1 = 120, 90, 5, 40
HOME_CLOSE = 5
BLOB_GAP = 3
BLOB_MIN_AREA = 20
DIGIT_H_FRAC = 0.45
DIGIT_LIT_ROWS = 0.6
SEP_CY_FRAC = 0.6
SEP_H_FRAC = 0.3
DIGIT_PAD_RATIO = 0.62
DIGIT_W, DIGIT_H = 12, 20
ADRIAN_CELLS = [(28, 78), (92, 141), (182, 232), (247, 296)]
ADRIAN_Y0, ADRIAN_Y1 = 10, 82
ADRIAN_V, ADRIAN_S = 110, 90
ADRIAN_CLOSE = 9
BLANK = 0.04
FILL_GAP_HOME = 130
FILL_GAP_AWAY = 5
BRIDGE_MAX_LEN = 130
BRIDGE_JUMP = 20
BRIDGE_BACK_TOL = 3
ZERO_HOLD = 3
RESET_JUMP = 30
RESET_HOLD_SLACK = 5
RESET_LOOKAHEAD = 6
MIN_STOPS = 3
GAME_GAP_MS = 8 * 60000
STOP_S = 5
TIP_PAD, BUZZ_PAD, FT_MAX = 2000, 3000, 90000
TIP_LOOKBACK = 8
L_ROUND = 30
L_TOL = 2
DROP_WARN_MS = 4 * 60000
_CLOCK_MSS = re.compile(r"^(\d{1,2}):([0-5]\d)$")
_CLOCK_TENTHS = re.compile(r"^(\d{1,2})\.(\d)$")
_DOTFIX = re.compile(r"^(\d\d):(\d)$")
_FT_REASONS = frozenset({"free_throw_line", "maybe_free_throw"})


def parse_clock(text: Any) -> float | None:
    """V11: M:SS (0-12 min) or SS.t / S.t (< 60 s) -> seconds; else None."""
    if not isinstance(text, str):
        return None
    s = text.strip()
    m = _CLOCK_MSS.fullmatch(s)
    if m:
        minutes = int(m.group(1))
        if minutes > 12:
            return None
        return float(minutes * 60 + int(m.group(2)))
    m = _CLOCK_TENTHS.fullmatch(s)
    if m:
        whole = int(m.group(1))
        tenths = int(m.group(2))
        if whole >= 60:
            return None
        return float(whole) + tenths / 10.0
    return None


def norm_read(s: Any) -> Any:
    """M:SS always has two digits after the colon; 'DD:D' is SS.t with the dot misread."""
    if isinstance(s, str) and _DOTFIX.match(s):
        return _DOTFIX.sub(r"\1.\2", s)
    return s


def find_board(video: str | Path) -> list[int]:
    """S1: dark static rectangle in bottom-right; largest connected component."""
    path = Path(video)
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise SystemExit(f"cannot open video: {path}")
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if n <= 0:
        cap.release()
        raise SystemExit("board not found")
    frames: list[np.ndarray] = []
    for i in range(BOARD_PROBE_N):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(n * (i + 0.5) / BOARD_PROBE_N))
        ok, f = cap.read()
        if ok and f is not None:
            frames.append(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32))
    cap.release()
    if not frames:
        raise SystemExit("board not found")
    st = np.stack(frames)
    h, w = st.shape[1:]
    dark = (st < BOARD_DARK_GRAY).mean(axis=0)
    mask = (dark > BOARD_DARK_FRAC).astype(np.uint8)
    mask[: int(h * 0.5), :] = 0
    mask[:, : int(w * 0.5)] = 0
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_CLOSE, np.ones((BOARD_CLOSE, BOARD_CLOSE), np.uint8)
    )
    num, _lab, stats, _ = cv2.connectedComponentsWithStats(mask)
    if num <= 1:
        raise SystemExit("board not found")
    best = max(range(1, num), key=lambda k: stats[k, cv2.CC_STAT_AREA])
    x, y, bw, bh = (int(stats[best, k]) for k in range(4))
    return [x, y, bw, bh]


def _board_image(frame: np.ndarray, box: list[int] | tuple[int, int, int, int]) -> np.ndarray:
    x, y, w, h = (int(v) for v in box)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    crop = gray[y : y + h, x : x + w]
    return cv2.resize(crop, (BOARD_REF_W, BOARD_REF_H), interpolation=cv2.INTER_AREA).astype(
        np.float32
    )


def _mean_board_image(video: str | Path, box: list[int]) -> np.ndarray:
    path = Path(video)
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise SystemExit(f"cannot open video: {path}")
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    imgs: list[np.ndarray] = []
    for i in range(BOARD_PROBE_N):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(n * (i + 0.5) / BOARD_PROBE_N))
        ok, f = cap.read()
        if ok and f is not None:
            imgs.append(_board_image(f, box))
    cap.release()
    if not imgs:
        raise SystemExit("board not found")
    return np.mean(np.stack(imgs), axis=0)


def load_templates(board: str) -> dict[str, Any]:
    path = TEMPLATES_DIR / f"{board}.npz"
    if not path.is_file():
        raise SystemExit(f"missing board templates: {path}")
    data = np.load(path, allow_pickle=True)
    return {
        "X": data["X"].astype(np.float32),
        "y": np.asarray(data["y"]).astype(str),
        "ref": data["ref"].astype(np.float32),
        "max_dist": float(np.asarray(data["max_dist"]).reshape(())),
    }


def board_distances(video: str | Path, box: list[int]) -> dict[str, float]:
    film = _mean_board_image(video, box)
    out: dict[str, float] = {}
    for name in ("home", "away_adrian"):
        tmpl = load_templates(name)
        out[name] = float(np.mean(np.abs(film - tmpl["ref"])))
    return out


def board_type(video: str | Path, box: list[int]) -> str:
    """S1 board type: nearest reference; stop if farther than 1.5 x max_dist."""
    dists = board_distances(video, box)
    typ = min(dists, key=dists.get)
    tmpl = load_templates(typ)
    if dists[typ] > BOARD_NEW_MULT * tmpl["max_dist"]:
        raise SystemExit("new board: mark ~20 seen frames")
    return typ


def clock_crop(frame: np.ndarray, box: list[int], board: str) -> np.ndarray:
    x, y, w, h = (int(v) for v in box)
    a, b, c, d = HOME_CROP if board == "home" else AWAY_CROP
    crop = frame[y + int(c * h) : y + int(d * h), x + int(a * w) : x + int(b * w)]
    return cv2.resize(
        crop,
        (int(crop.shape[1] * SCALE_H / crop.shape[0]), SCALE_H),
        interpolation=cv2.INTER_CUBIC,
    )


def _lit_mask_home(crop: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    m = (
        (hsv[..., 2] > HOME_V)
        & (hsv[..., 1] > HOME_S)
        & (hsv[..., 0] >= HOME_H0)
        & (hsv[..., 0] <= HOME_H1)
    ).astype(np.uint8)
    return cv2.morphologyEx(
        m, cv2.MORPH_CLOSE, np.ones((HOME_CLOSE, HOME_CLOSE), np.uint8)
    )


def blobs(crop: np.ndarray) -> tuple[list[tuple[int, int, int, int, str]], np.ndarray]:
    """Return list of (x0, x1, y0, y1, kind) left to right; kind 'd' digit or 's' separator."""
    m = _lit_mask_home(crop)
    col = m.sum(axis=0) > 0
    runs: list[list[int]] = []
    i, W = 0, len(col)
    while i < W:
        if col[i]:
            j = i
            while j < W and col[j]:
                j += 1
            runs.append([i, j])
            i = j
        else:
            i += 1
    merged: list[list[int]] = []
    for r in runs:
        if merged and r[0] - merged[-1][1] <= BLOB_GAP:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    out: list[tuple[int, int, int, int, str]] = []
    for x0, x1 in merged:
        rows = np.where(m[:, x0:x1].sum(axis=1) > 0)[0]
        if len(rows) == 0:
            continue
        y0, y1 = int(rows[0]), int(rows[-1]) + 1
        if (x1 - x0) * (y1 - y0) < BLOB_MIN_AREA:
            continue
        lit_rows = (m[y0:y1, x0:x1].sum(axis=1) > 0).mean()
        kind = (
            "d"
            if (y1 - y0) >= DIGIT_H_FRAC * SCALE_H and lit_rows >= DIGIT_LIT_ROWS
            else "s"
        )
        out.append((x0, x1, y0, y1, kind))
    return out, m


def digit_vec(m: np.ndarray, b: tuple[int, int, int, int, str]) -> np.ndarray:
    x0, x1, y0, y1, _ = b
    g = m[y0:y1, x0:x1].astype(np.float32)
    h, w = g.shape
    W = max(w, int(h * DIGIT_PAD_RATIO))
    pad = np.zeros((h, W), np.float32)
    pad[:, W - w :] = g
    return cv2.resize(pad, (DIGIT_W, DIGIT_H), interpolation=cv2.INTER_AREA).ravel()


def _sep_char(m: np.ndarray, b: tuple[int, int, int, int, str]) -> str:
    x0, x1, y0, y1, _ = b
    cy = (y0 + y1) / 2
    return (
        "."
        if cy > SEP_CY_FRAC * SCALE_H and (y1 - y0) < SEP_H_FRAC * SCALE_H
        else ":"
    )


def read_home(crop: np.ndarray, templates: dict[str, Any]) -> str:
    X, y = templates["X"], templates["y"]
    bl, mk = blobs(crop)
    s = ""
    for b in bl:
        if b[4] == "d":
            v = digit_vec(mk, b)
            s += str(y[int(np.argmin(((X - v) ** 2).sum(axis=1)))])
        else:
            s += _sep_char(mk, b)
    return s


def _adrian_mask(crop: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    m = (
        (hsv[..., 2] > ADRIAN_V)
        & (hsv[..., 1] > ADRIAN_S)
        & (hsv[..., 0] >= HOME_H0)
        & (hsv[..., 0] <= HOME_H1)
    ).astype(np.uint8)
    return cv2.morphologyEx(
        m, cv2.MORPH_CLOSE, np.ones((ADRIAN_CLOSE, ADRIAN_CLOSE), np.uint8)
    )


def _cell_vecs(crop: np.ndarray) -> list[tuple[float, np.ndarray]]:
    m = _adrian_mask(crop)
    out: list[tuple[float, np.ndarray]] = []
    for x0, x1 in ADRIAN_CELLS:
        g = m[ADRIAN_Y0:ADRIAN_Y1, x0:x1].astype(np.float32)
        out.append(
            (
                float(g.mean()),
                cv2.resize(g, (DIGIT_W, DIGIT_H), interpolation=cv2.INTER_AREA).ravel(),
            )
        )
    return out


def read_adrian(
    crop: np.ndarray, templates: dict[str, Any]
) -> tuple[str | None, int | None]:
    """-> ('mss', seconds) | ('sst', tenths) | (None, None)"""
    X, y = templates["X"], templates["y"]
    cv = _cell_vecs(crop)

    def nn(v: np.ndarray) -> str:
        return str(y[int(np.argmin(((X - v) ** 2).sum(axis=1)))])

    if cv[2][0] < BLANK:
        return None, None
    if cv[3][0] >= BLANK:
        return "mss", int(nn(cv[2][1])) * 10 + int(nn(cv[3][1]))
    return "sst", int(nn(cv[2][1]))


def sample_film(video: str | Path, box: list[int] | None = None, board: str | None = None) -> list[dict[str, Any]]:
    """Raw per-second (+ half-second) clock reads. Same shape as design48b reference raw files."""
    path = Path(video)
    if box is None:
        box = find_board(path)
    if board is None:
        board = board_type(path, box)
    templates = load_templates(board)
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise SystemExit(f"cannot open video: {path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0) or 30.0
    step = int(round(fps))
    half = step // 2
    out: list[dict[str, Any]] = []
    i = 0
    while cap.grab():
        if board == "home":
            if i % step == 0 or (i % step == half and out):
                ok, fr = cap.retrieve()
                if ok and fr is not None:
                    s = read_home(clock_crop(fr, box, board), templates)
                    if i % step == 0:
                        out.append(
                            {
                                "t_ms": int(round(i / fps * 1000)),
                                "read": s,
                                "clock_s": parse_clock(s),
                                "read2": None,
                            }
                        )
                    else:
                        out[-1]["read2"] = s
        else:
            if i % step == 0:
                ok, fr = cap.retrieve()
                if ok and fr is not None:
                    fmt, v = read_adrian(clock_crop(fr, box, board), templates)
                    out.append(
                        {
                            "t_ms": int(round(i / fps * 1000)),
                            "fmt": fmt,
                            "v": v,
                            "fmt2": None,
                            "v2": None,
                        }
                    )
            elif i % step == half and out:
                ok, fr = cap.retrieve()
                if ok and fr is not None:
                    out[-1]["fmt2"], out[-1]["v2"] = read_adrian(
                        clock_crop(fr, box, board), templates
                    )
        i += 1
    cap.release()
    return out


def states_partial(raw: list[dict[str, Any]]) -> list[str | None]:
    """Adrian-type: fmt/v (+fmt2/v2 half-second read)."""
    st: list[str | None] = [None] * len(raw)
    for k in range(1, len(raw)):
        a, b = raw[k - 1], raw[k]
        if b["fmt"] is None or a["fmt"] is None:
            continue
        if b["fmt"] == "mss" and a["fmt"] == "mss":
            if b["v"] == a["v"]:
                st[k] = "stop"
            elif b["v"] == (a["v"] - 1) % 60 or b["v"] == (a["v"] - 2) % 60:
                st[k] = "run"
        elif b["fmt"] == "sst":
            if b.get("fmt2") == "sst" and b.get("v2") is not None:
                st[k] = (
                    "run"
                    if b["v2"] != b["v"]
                    else ("stop" if a["fmt"] == "sst" and a["v"] == b["v"] else None)
                )
    return st


def states_full(raw: list[dict[str, Any]]) -> list[str | None]:
    """Home-type: clock_s (+read2 at 0.5 s)."""
    st: list[str | None] = [None] * len(raw)
    for k in range(1, len(raw)):
        a, b = raw[k - 1]["clock_s"], raw[k]["clock_s"]
        if a is None or b is None:
            continue
        d = a - b
        if abs(d) < 0.05:
            st[k] = "stop"
        elif 0.5 <= d <= 2.05:
            st[k] = "run"
    return st


def fill(st: list[str | None], max_gap: int = 5) -> list[str | None]:
    """Carry the last known state across short unknown gaps."""
    out: list[str | None] = []
    last: str | None = None
    gap = 0
    for s in st:
        if s is None:
            gap += 1
            out.append(last if gap <= max_gap else None)
        else:
            last, gap = s, 0
            out.append(s)
    return out


def bridge_excursions(
    clock: list[float | None],
    max_len: int = BRIDGE_MAX_LEN,
    jump: float = BRIDGE_JUMP,
    back_tol: float = BRIDGE_BACK_TOL,
) -> tuple[list[float | None], list[int]]:
    """Timeout/break timers: leave P and return near P -> samples in between become None."""
    c = list(clock)
    n, k, bridged = len(c), 1, []
    last = None
    while k < n:
        if c[k - 1] is not None:
            last = c[k - 1]
        if last is not None and c[k] is not None and abs(c[k] - last) > jump:
            ret = None
            for j in range(k + 1, min(n, k + max_len)):
                if c[j] is not None and abs(c[j] - last) <= back_tol:
                    nxt = [x for x in c[j : j + 5] if x is not None][:3]
                    if len(nxt) == 3 and all(abs(x - last) <= back_tol + 3 for x in nxt):
                        ret = j
                        break
            if ret is not None:
                for i in range(k, ret):
                    c[i] = None
                    bridged.append(i)
                k = ret
                continue
        k += 1
    return c, bridged


def zero_ends(is_zero: list[bool], t_ms: list[int]) -> list[tuple[int, int]]:
    """Indices where a held zero starts. Stray reads (<=2 consecutive) inside the hold are ignored."""
    out: list[tuple[int, int]] = []
    n, k = len(is_zero), 0
    while k < n:
        if is_zero[k]:
            j, last, bad = k, k, 0
            while j < n and bad <= 2:
                if is_zero[j]:
                    last, bad = j, 0
                else:
                    bad += 1
                j += 1
            zs = sum(is_zero[k : last + 1])
            if zs >= ZERO_HOLD:
                out.append((k, last))
            k = last + 1
        else:
            k += 1
    return out


def resets_full(clock: list[float | None]) -> list[int]:
    out: list[int] = []
    n = len(clock)
    for k in range(1, n):
        prev = next((clock[j] for j in range(k - 1, -1, -1) if clock[j] is not None), None)
        if prev is None or clock[k] is None or clock[k] < prev + RESET_JUMP:
            continue
        nxt = [c for c in clock[k : k + RESET_LOOKAHEAD] if c is not None][:3]
        if len(nxt) == 3 and all(abs(c - clock[k]) <= RESET_HOLD_SLACK for c in nxt):
            out.append(k)
    return out


def resets_partial(raw: list[dict[str, Any]]) -> list[int]:
    out: list[int] = []
    for k in range(1, len(raw)):
        if (
            raw[k]["fmt"] == "mss"
            and raw[k - 1]["fmt"] == "sst"
            and all(r["fmt"] == "mss" for r in raw[k : k + 3])
        ):
            out.append(k)
    return out


def build(
    st: list[str | None],
    is_zero: list[bool],
    t_ms: list[int],
    resets: list[int],
    clock: list[float | None] | None = None,
) -> dict[str, Any]:
    """S6-S7 session build (design session_v3) plus S7b dropped_segments/warnings."""
    n = len(st)
    cuts: set[tuple[str, int, int]] = set()
    for a, z in zero_ends(is_zero, t_ms):
        cuts.add(("z", a, z))
    for k in resets:
        cuts.add(("r", k, k))
    cuts_list = sorted(cuts, key=lambda c: c[1])
    segs: list[tuple[int, int, str, int]] = []
    lo = 0
    for kind, a, z in cuts_list:
        if a > lo:
            segs.append((lo, a, kind, z))
        lo = max(lo, z + 1 if kind == "z" else a)
    if lo < n:
        segs.append((lo, n, "end", n - 1))
    info: list[dict[str, Any]] = []
    for lo, hi, kind, z in segs:
        stops, k = 0, lo + 1
        while k < hi:
            if st[k - 1] == "run" and st[k] == "stop":
                j = k
                while j < hi and st[j] == "stop":
                    j += 1
                if j - k >= STOP_S:
                    stops += 1
                k = j
            else:
                k += 1
        tip = next((k for k in range(lo, hi) if st[k] == "run"), None)
        start_val = None
        if clock is not None and tip is not None:
            vals = [
                clock[k]
                for k in range(max(lo, tip - TIP_LOOKBACK), tip + 1)
                if clock[k] is not None
            ]
            start_val = max(vals) if vals else None
        info.append(
            dict(lo=lo, hi=hi, kind=kind, z=z, stops=stops, tip=tip, start_val=start_val)
        )
    conf_starts = [
        round(i["start_val"] / L_ROUND) * L_ROUND
        for i in info
        if i["tip"] is not None and i["stops"] >= MIN_STOPS and i["start_val"]
    ]
    L = max(set(conf_starts), key=conf_starts.count) if conf_starts else None
    intervals: list[dict[str, int]] = []
    fts: list[dict[str, int]] = []
    periods: list[dict[str, Any]] = []
    dropped_segments: list[dict[str, Any]] = []
    count, last_end = 0, None
    for i in info:
        if i["tip"] is None:
            continue
        lo, hi, kind, z, tip = i["lo"], i["hi"], i["kind"], i["z"], i["tip"]
        if last_end is not None and t_ms[tip] - last_end > GAME_GAP_MS:
            count = 0
        reason = None
        if i["stops"] >= MIN_STOPS:
            is_period = True
        elif i["stops"] == 0:
            is_period = False
            reason = "timer: 0 stops"
        elif count == 2:
            is_period = False
            reason = "halftime: 1-2 stops after period 2"
        elif L is not None and i["start_val"] is not None:
            is_period = abs(i["start_val"] - L) <= L_TOL
            if not is_period:
                reason = "1-2 stops, not at L"
        else:
            is_period = count == 3
            if not is_period:
                reason = "1-2 stops, partial board, not after period 3"
        if not is_period:
            dropped_segments.append(
                {
                    "start_ms": int(t_ms[lo]),
                    "end_ms": int(t_ms[hi - 1]),
                    "stops": i["stops"],
                    "start_val": i["start_val"],
                    "reason": reason,
                }
            )
            continue
        count = count + 1 if count < 4 else 1
        end_i = min(hi if kind == "z" else hi - 1, n - 1)
        last_run = max((k for k in range(lo, hi) if st[k] == "run"), default=tip)
        e_ms = (t_ms[end_i] if kind == "z" else t_ms[last_run]) + BUZZ_PAD
        s_ms = t_ms[tip] - TIP_PAD
        last_end = e_ms
        intervals.append({"start_ms": s_ms, "end_ms": e_ms})
        periods.append(
            {
                "start_ms": s_ms,
                "end_ms": e_ms,
                "stops": i["stops"],
                "end": kind,
                "n_in_game": count,
            }
        )
        if kind == "z":
            fe = min(t_ms[z], t_ms[end_i] + FT_MAX)
            if fe > e_ms:
                fts.append({"start_ms": e_ms, "end_ms": fe})
    warnings: list[str] = []
    if periods:
        games: list[list[dict[str, Any]]] = []
        cur: list[dict[str, Any]] = []
        for p in periods:
            if p["n_in_game"] == 1 and cur:
                games.append(cur)
                cur = [p]
            else:
                cur.append(p)
        if cur:
            games.append(cur)
        for g in games:
            if len(g) != 4:
                warnings.append(f"game with {len(g)} periods (not 4)")
    for d in dropped_segments:
        if int(d["end_ms"]) - int(d["start_ms"]) >= DROP_WARN_MS:
            warnings.append(
                f"dropped segment >= 4 min ({d['start_ms']}-{d['end_ms']})"
            )
    return {
        "L": L,
        "periods": periods,
        "intervals": intervals,
        "ft_windows": fts,
        "error": None if intervals else "no periods",
        "dropped_segments": dropped_segments,
        "warnings": warnings,
    }


def session_from_raw(raw: list[dict[str, Any]], board: str) -> dict[str, Any]:
    """Exact eval_v3 glue: home uses bridge/fill-130; away_adrian uses fill default gap 5."""
    if board == "away_adrian":
        st = fill(states_partial(raw))
        z = [
            r["fmt"] == "sst" and r["v"] == 0 and r.get("v2") in (0, None) for r in raw
        ]
        t = [r["t_ms"] for r in raw]
        rs = resets_partial(raw)
        return build(st, z, t, rs, clock=None)
    for r in raw:
        r["clock_s"] = parse_clock(norm_read(r["read"]))
        r["read2"] = norm_read(r.get("read2"))
    cl, _br = bridge_excursions([r["clock_s"] for r in raw])
    for r, c in zip(raw, cl):
        r["clock_s"] = c
    st = fill(states_full(raw), max_gap=FILL_GAP_HOME)
    z = [r["clock_s"] == 0 and parse_clock(r.get("read2")) in (0, None) for r in raw]
    t = [r["t_ms"] for r in raw]
    rs = resets_full([r["clock_s"] for r in raw])
    return build(st, z, t, rs, clock=[r["clock_s"] for r in raw])


def in_session(t_ms: int, session: dict[str, Any], is_ft: bool = False) -> bool:
    t = int(t_ms)
    for iv in session.get("intervals") or []:
        if int(iv["start_ms"]) <= t <= int(iv["end_ms"]):
            return True
    if is_ft:
        for iv in session.get("ft_windows") or []:
            if int(iv["start_ms"]) < t <= int(iv["end_ms"]):
                return True
    return False


def _moment_is_ft(moment: dict[str, Any]) -> bool:
    return moment.get("ft_reason") in _FT_REASONS


def filter_moments(session: dict[str, Any], moments: list[dict[str, Any]]) -> dict[str, Any]:
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for m in moments:
        t = int(m.get("t_ms", m.get("timestamp_ms", m.get("t", -1))))
        is_ft = _moment_is_ft(m)
        if in_session(t, session, is_ft=is_ft):
            kept.append(m)
        else:
            dropped.append(m)
    return {"kept": kept, "dropped": dropped}


def sheet(
    items: list[tuple[np.ndarray, list, str]], path: str | Path, cols: int = 4
) -> None:
    """digits48.sheet layout: 4 columns, crop with boxes, caption = t_ms and read."""
    tiles = []
    for crop, bl, cap in items:
        t = crop.copy()
        for _k, box in enumerate(bl):
            if len(box) == 5:
                x0, x1, y0, y1, kind = box
                color = (0, 255, 0) if kind == "d" else (255, 0, 255)
                cv2.rectangle(t, (x0, y0), (x1 - 1, y1 - 1), color, 1)
            else:
                x0, y0, x1, y1 = box
                cv2.rectangle(t, (x0, y0), (x1, y1), (0, 255, 0), 1)
        t = cv2.resize(t, (300, int(300 * t.shape[0] / t.shape[1])))
        lab = np.zeros((26, 300, 3), np.uint8)
        cv2.putText(lab, cap, (3, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
        tiles.append(cv2.vconcat([t, lab]))
    H = max(t.shape[0] for t in tiles)
    tiles = [
        cv2.copyMakeBorder(t, 0, H - t.shape[0], 0, 4, cv2.BORDER_CONSTANT) for t in tiles
    ]
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    cv2.imwrite(
        str(path),
        cv2.vconcat([cv2.hconcat(tiles[r : r + cols]) for r in range(0, len(tiles), cols)]),
    )


def cmd_run(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    if out_dir.exists():
        raise SystemExit(f"out-dir exists: {out_dir}")
    out_dir.mkdir(parents=True)
    video = Path(args.video)
    box = find_board(video)
    dists = board_distances(video, box)
    board = min(dists, key=dists.get)
    tmpl = load_templates(board)
    if dists[board] > BOARD_NEW_MULT * tmpl["max_dist"]:
        raise SystemExit("new board: mark ~20 seen frames")
    cap = cv2.VideoCapture(str(video))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0) or 30.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    cap.release()
    boxes = {
        "box": box,
        "board": board,
        "distances": dists,
        "video_size": {"width": width, "height": height},
        "fps": fps,
        "frame_count": frame_count,
    }
    (out_dir / "boxes.json").write_text(json.dumps(boxes, indent=2), encoding="utf-8")
    samples = sample_film(video, box=box, board=board)
    (out_dir / "samples.json").write_text(json.dumps(samples, indent=2), encoding="utf-8")
    session = session_from_raw(samples, board)
    payload = {
        "film": args.film_id,
        "video": str(video),
        "board": board,
        "L": session.get("L"),
        "periods": session.get("periods") or [],
        "intervals": session.get("intervals") or [],
        "ft_windows": session.get("ft_windows") or [],
        "dropped_segments": session.get("dropped_segments") or [],
        "warnings": session.get("warnings") or [],
        "error": session.get("error"),
    }
    (out_dir / "session.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("periods:", json.dumps(payload["periods"], indent=2))
    print("dropped_segments:", json.dumps(payload["dropped_segments"], indent=2))
    print("warnings:", json.dumps(payload["warnings"], indent=2))
    if payload["error"]:
        return 1
    return 0


def cmd_check_reader(args: argparse.Namespace) -> int:
    video = Path(args.video)
    box = find_board(video)
    board = board_type(video, box)
    templates = load_templates(board)
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise SystemExit(f"cannot open video: {video}")
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0) or 30.0
    rng = random.Random(int(args.seed))
    n = int(args.n)
    idx: list[int] = []
    while len(idx) < n and n_frames > 0:
        i = rng.randrange(n_frames)
        if all(abs(i - e) > fps * 5 for e in idx):
            idx.append(i)
    items = []
    reads: list[tuple[int, Any]] = []
    for i in sorted(idx):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, fr = cap.read()
        if not ok or fr is None:
            continue
        t_ms = int(i / fps * 1000)
        crop = clock_crop(fr, box, board)
        if board == "home":
            text = read_home(crop, templates)
            bl, _mk = blobs(crop)
            items.append((crop, bl, f"{t_ms} {text}"))
            reads.append((t_ms, text))
            print(f"t_ms={t_ms} read={text!r}")
        else:
            fmt, v = read_adrian(crop, templates)
            cells = [(x0, ADRIAN_Y0, x1, ADRIAN_Y1) for x0, x1 in ADRIAN_CELLS]
            items.append((crop, cells, f"{t_ms} {fmt}:{v}"))
            reads.append((t_ms, (fmt, v)))
            print(f"t_ms={t_ms} read={fmt!r},{v!r}")
    cap.release()
    if items:
        sheet(items, args.out, cols=4)
    print(f"reads {len(reads)}/{n}")
    return 0


def cmd_filter(args: argparse.Namespace) -> int:
    session = json.loads(Path(args.session).read_text(encoding="utf-8"))
    moments = json.loads(Path(args.moments_json).read_text(encoding="utf-8"))
    if isinstance(moments, dict):
        moments = moments.get("moments") or moments.get("items") or []
    result = filter_moments(session, moments)
    Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="game_session")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run")
    p_run.add_argument("--video", required=True)
    p_run.add_argument("--film-id", required=True)
    p_run.add_argument("--out-dir", required=True)
    p_run.set_defaults(func=cmd_run)

    p_chk = sub.add_parser("check-reader")
    p_chk.add_argument("--video", required=True)
    p_chk.add_argument("--out", required=True)
    p_chk.add_argument("--n", type=int, default=30)
    p_chk.add_argument("--seed", type=int, default=48)
    p_chk.set_defaults(func=cmd_check_reader)

    p_flt = sub.add_parser("filter")
    p_flt.add_argument("--session", required=True)
    p_flt.add_argument("--moments-json", required=True)
    p_flt.add_argument("--out", required=True)
    p_flt.set_defaults(func=cmd_filter)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
