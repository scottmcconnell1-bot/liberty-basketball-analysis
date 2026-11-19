"""Per-second clock state from readings: 'run' (ticks down by 1), 'stop' (same), None (unknown/misread)."""
import numpy as np


def states_partial(raw):
    """Adrian-type: fmt/v (+fmt2/v2 half-second read)."""
    st = [None] * len(raw)
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
                st[k] = "run" if b["v2"] != b["v"] else ("stop" if a["fmt"] == "sst" and a["v"] == b["v"] else None)
    return st


def states_full(raw):
    """Home-type: clock_s (+read2 at 0.5 s)."""
    st = [None] * len(raw)
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


def fill(st, max_gap=5):
    """Carry the last known state across short unknown gaps."""
    out, last, gap = [], None, 0
    for s in st:
        if s is None:
            gap += 1
            out.append(last if gap <= max_gap else None)
        else:
            last, gap = s, 0
            out.append(s)
    return out


def stoppages(st, min_stop=3):
    """Indices where a stop of >= min_stop s begins after running."""
    idx, k, n = [], 1, len(st)
    while k < n:
        if st[k - 1] == "run" and st[k] == "stop":
            j = k
            while j < n and st[j] == "stop":
                j += 1
            if j - k >= min_stop:
                idx.append(k)
            k = j
        else:
            k += 1
    return idx
