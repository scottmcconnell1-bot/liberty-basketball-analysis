"""Session v3 (design): split at held zero or reset; a segment is play if it has >= MIN_STOPS stoppages."""
from session_v2 import zero_ends
MIN_STOPS = 3
DEBUG = []
GAME_GAP_MS = 8 * 60000   # no period for 8 min = between games
STOP_S = 5
TIP_PAD, BUZZ_PAD, FT_MAX = 2000, 3000, 90000


def resets_full(clock):
    out, n = [], len(clock)
    for k in range(1, n):
        prev = next((clock[j] for j in range(k - 1, -1, -1) if clock[j] is not None), None)
        if prev is None or clock[k] is None or clock[k] < prev + 30:
            continue
        nxt = [c for c in clock[k:k + 6] if c is not None][:3]
        if len(nxt) == 3 and all(abs(c - clock[k]) <= 5 for c in nxt):
            out.append(k)
    return out


def resets_partial(raw):
    out = []
    for k in range(1, len(raw)):
        if raw[k]["fmt"] == "mss" and raw[k - 1]["fmt"] == "sst" and all(r["fmt"] == "mss" for r in raw[k:k + 3]):
            out.append(k)
    return out


def build(st, is_zero, t_ms, resets, clock=None):
    n = len(st)
    cuts = set()
    for a, z in zero_ends(is_zero, t_ms):
        cuts.add(("z", a, z))
    for k in resets:
        cuts.add(("r", k, k))
    cuts = sorted(cuts, key=lambda c: c[1])
    segs, lo = [], 0
    for kind, a, z in cuts:
        if a > lo:
            segs.append((lo, a, kind, z))   # segment [lo, a); ends at a zero (kind z) or reset
        lo = max(lo, z + 1 if kind == "z" else a)
    if lo < n:
        segs.append((lo, n, "end", n - 1))
    # pass 1: measure each segment
    info = []
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
            vals = [clock[k] for k in range(max(lo, tip - 8), tip + 1) if clock[k] is not None]
            start_val = max(vals) if vals else None
        DEBUG.append((t_ms[lo], t_ms[hi - 1], stops, tip is not None))
        info.append(dict(lo=lo, hi=hi, kind=kind, z=z, stops=stops, tip=tip, start_val=start_val))
    # L = most common start value (nearest 30 s) of confirmed periods (full boards only)
    conf_starts = [round(i["start_val"] / 30) * 30 for i in info if i["tip"] is not None and i["stops"] >= MIN_STOPS and i["start_val"]]
    L = max(set(conf_starts), key=conf_starts.count) if conf_starts else None
    # pass 2: classify in order. >= MIN_STOPS: period. 0: timer. 1..MIN_STOPS-1: uncertain ->
    # halftime if it comes right after the 2nd period of a game; else a period if it starts at L
    # (partial boards with unknown L: a period only right after the 3rd period).
    intervals, fts, periods = [], [], []
    count, last_end = 0, None
    for i in info:
        if i["tip"] is None:
            continue
        lo, hi, kind, z, tip = i["lo"], i["hi"], i["kind"], i["z"], i["tip"]
        if last_end is not None and t_ms[tip] - last_end > GAME_GAP_MS:
            count = 0                      # a new game
        if i["stops"] >= MIN_STOPS:
            is_period = True
        elif i["stops"] == 0:
            is_period = False
        elif count == 2:
            is_period = False              # halftime
        elif L is not None and i["start_val"] is not None:
            is_period = abs(i["start_val"] - L) <= 2
        else:
            is_period = count == 3
        if not is_period:
            continue
        count = count + 1 if count < 4 else 1
        end_i = min(hi if kind == "z" else hi - 1, n - 1)
        last_run = max((k for k in range(lo, hi) if st[k] == "run"), default=tip)
        e_ms = (t_ms[end_i] if kind == "z" else t_ms[last_run]) + BUZZ_PAD
        s_ms = t_ms[tip] - TIP_PAD
        last_end = e_ms
        intervals.append({"start_ms": s_ms, "end_ms": e_ms})
        periods.append({"start_ms": s_ms, "end_ms": e_ms, "stops": i["stops"], "end": kind, "n_in_game": count})
        if kind == "z":
            fe = min(t_ms[z], t_ms[end_i] + FT_MAX)
            if fe > e_ms:
                fts.append({"start_ms": e_ms, "end_ms": fe})
    return {"L": L, "periods": periods, "intervals": intervals, "ft_windows": fts, "error": None if intervals else "no periods"}


import re
_DOTFIX = re.compile(r"^(\d\d):(\d)$")


def norm_read(s):
    """M:SS always has two digits after the colon; 'DD:D' is SS.t with the dot misread."""
    if isinstance(s, str) and _DOTFIX.match(s):
        return _DOTFIX.sub(r"\1.\2", s)
    return s


def bridge_excursions(clock, max_len=130, jump=20, back_tol=3):
    """Timeout/break timers shown in place of the game clock: the clock leaves value P and later returns
    to within back_tol of P (never above P+back_tol). Those samples become None. Returns (clock, bridged idx)."""
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
                    nxt = [x for x in c[j:j + 5] if x is not None][:3]
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
