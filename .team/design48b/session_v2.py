"""Session v2 (design): zero-end splits + timer exclusion + tip."""
TIMER_S = 150      # continuous running this long = a timer (warm-up / halftime), not play
ZERO_HOLD = 3      # zero held >= 3 samples (with <=2 stray reads) = period end
TIP_PAD, BUZZ_PAD, FT_MAX = 2000, 3000, 90000


def zero_ends(is_zero, t_ms):
    """Indices where a held zero starts. Stray reads (<=2 consecutive) inside the hold are ignored."""
    out, n, k = [], len(is_zero), 0
    while k < n:
        if is_zero[k]:
            j, last, bad = k, k, 0
            while j < n and bad <= 2:
                if is_zero[j]:
                    last, bad = j, 0
                else:
                    bad += 1
                j += 1
            zs = sum(is_zero[k:last + 1])
            if zs >= ZERO_HOLD:
                out.append((k, last))
            k = last + 1
        else:
            k += 1
    return out


def run_streaks(st, minlen, allow=2):
    out, k, n = [], 0, len(st)
    while k < n:
        if st[k] == "run":
            j, last, bad = k, k, 0
            while j < n and bad <= allow:
                if st[j] == "run":
                    last, bad = j, 0
                else:
                    bad += 1
                j += 1
            if last - k + 1 >= minlen:
                out.append((k, last))
            k = last + 1
        else:
            k += 1
    return out


def build(st, is_zero, t_ms):
    n = len(st)
    ends = zero_ends(is_zero, t_ms)
    timers = run_streaks(st, TIMER_S)
    bounds = [(-1, -1)] + ends + ([] if ends and ends[-1][1] >= n - 3 else [(n - 1, n - 1)])
    intervals, fts, periods = [], [], []
    for (pa, pz), (za, zz) in zip(bounds[:-1], bounds[1:]):
        lo = pz + 1
        for ta, tz in timers:
            if lo <= tz <= za:
                lo = max(lo, tz + 1)
        tip = next((k for k in range(lo, za + 1) if st[k] == "run"), None)
        if tip is None:
            continue
        s, e = t_ms[tip] - TIP_PAD, t_ms[za] + BUZZ_PAD
        intervals.append({"start_ms": s, "end_ms": e})
        periods.append({"start_ms": s, "end_ms": e, "film_end": za == n - 1 and not is_zero[za]})
        fe = min(t_ms[zz], t_ms[za] + FT_MAX) if is_zero[za] else e
        if fe > e:
            fts.append({"start_ms": e, "end_ms": fe})
    return {"L": None, "periods": periods, "intervals": intervals, "ft_windows": fts, "error": None if intervals else "no periods"}
