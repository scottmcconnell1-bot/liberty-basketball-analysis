"""Score stored shot rows against the coach's shot tags.

The count gate is three numbers on the coach's shot tags, and nothing else:

    right                  the tag and the program agree on make or miss
    makes_missed           the tag says make, the program did not store a make
    misses_called_makes    the tag says miss, the program stored a make

Every tag lands in exactly one bucket, so the three always sum to the tag count.
That is why the recorded best score on the Adrian film reads 85 + 20 + 6 = 111,
and why "call every shot a miss" on the same 111 tags reads 73 + 38 + 0.

A tag is predicted **make** when a stored make sits within the match tolerance of
it, and **miss** otherwise. A tag with no stored row at all is therefore predicted
miss -- not "unknown". The make/miss contract has no third value: a make on the
film is ``ball_through_rim`` or ``net_moved_after_shot``, and both false is a miss.

This module is deliberately standalone: no Flask, no database driver, no OpenCV,
so it runs from a bare interpreter on the home laptop and inside CI alike. The
caller supplies plain dictionaries. ``tests/test_shot_tag_gate.py`` checks the
tolerance and the clock parser against ``manual_tag_teach`` so the gate cannot
drift away from what the teach pass actually does.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

# Mirrors manual_tag_teach.MATCH_TOLERANCE_MS. Kept local so this module stays
# importable on its own; tests/test_shot_tag_gate.py fails if the two disagree.
MATCH_TOLERANCE_MS = 8000

SHOT_TAG_TYPES = ("2PT", "3PT", "FT")

# Stored event types that assert a made basket.
MADE_EVENT_TYPES = frozenset({"made_two", "made_three", "made_free_throw"})
# Stored event types that assert a shot that did not go in.
MISSED_EVENT_TYPES = frozenset({"missed_two", "missed_three", "missed_free_throw"})

# A rejected row is one a human threw out. It is not a claim by the program any
# more, so it cannot make a tag right and cannot make a miss into a make.
REJECTED_STATUSES = frozenset({"rejected", "reject"})

# A corrected row is one the teach pass fixed because a tag of the same family sat
# within the tolerance -- the tag supplied the answer. Counting it as the program's
# own make would grade the tags against themselves, so it is left out by default.
TAUGHT_STATUSES = frozenset({"corrected"})

METRICS = ("right", "makes_missed", "misses_called_makes")


def time_to_ms(value: Any) -> int:
    """Film Tool clock text (``"2:31.6"``, ``"151.6"``) to milliseconds.

    Mirrors manual_tag_teach.time_to_ms, including its habit of returning 0 for
    anything unparseable rather than raising.
    """
    text = str(value or "").strip()
    if not text:
        return 0
    parts = text.split(":")
    try:
        if len(parts) == 1:
            return int(round(float(parts[0]) * 1000))
        return int(round(((int(parts[0]) or 0) * 60 + float(parts[1] or 0)) * 1000))
    except (TypeError, ValueError):
        return 0


def _row_ms(row: dict) -> int:
    for field in ("timestamp_ms", "film_ms"):
        raw = row.get(field)
        if raw not in (None, ""):
            try:
                return int(float(raw))
            except (TypeError, ValueError):
                pass
    return time_to_ms(row.get("start") or row.get("clock"))


def shot_tags(rows: Iterable[dict]) -> list[dict]:
    """The coach's shot tags, in film order, as ``{ms, kind, made, label}``.

    Takes Film Tool tag rows (``eventtype`` ``2PT``/``3PT``/``FT`` and ``result``
    ``Make``/``Miss``) and ignores every other tag -- rebounds, fouls, subs and
    the rest are a different step.
    """
    tags = []
    for row in rows:
        kind = str(row.get("eventtype") or "").strip().upper()
        if kind not in SHOT_TAG_TYPES:
            continue
        result = str(row.get("result") or "").strip().lower()
        if result not in ("make", "made", "miss", "missed"):
            continue
        ms = _row_ms(row)
        tags.append({
            "ms": ms,
            "kind": kind,
            "made": result in ("make", "made"),
            "quarter": str(row.get("quarter") or "").strip(),
            "label": f"{kind} {'Make' if result in ('make', 'made') else 'Miss'} @ {ms}",
        })
    tags.sort(key=lambda t: t["ms"])
    return tags


def stored_makes(events: Iterable[dict], count_taught: bool = False) -> list[dict]:
    """Timestamps where the program stored a made basket, on its own.

    Reads either the typed precision rows (``made_two`` and friends) or a generic
    ``shot`` row carrying ``shot_result``. Three kinds of row are left out, because
    none of them is the program's own claim about the film:

    * rejected rows -- a human threw them out;
    * manual rows -- the coach's own tag, which cannot grade itself;
    * corrected rows -- the teach pass rewrote them from a tag inside the
      tolerance, so the answer came from the answer key.

    Pass ``count_taught=True`` to include corrected rows. That answers a different
    question ("what does the card say now"), not "how well does the program read
    the film", and it cannot be used to claim a gate score.
    """
    makes = []
    for event in events:
        event_type = str(event.get("event_type") or "").strip().lower()
        status = str(event.get("review_status") or event.get("status") or "").strip().lower()
        if status in REJECTED_STATUSES:
            continue
        if status in TAUGHT_STATUSES and not count_taught:
            continue
        if str(event.get("source_type") or "ai").strip().lower() == "manual":
            continue
        if event_type in MADE_EVENT_TYPES:
            made = True
        elif event_type in MISSED_EVENT_TYPES:
            made = False
        elif event_type == "shot":
            made = str(event.get("shot_result") or "").strip().lower() in ("make", "made")
        else:
            continue
        if made:
            makes.append({"ms": _row_ms(event), "event_type": event_type, "id": event.get("id")})
    makes.sort(key=lambda m: m["ms"])
    return makes


def score(
    tags: Sequence[dict],
    makes: Sequence[dict],
    tolerance_ms: int = MATCH_TOLERANCE_MS,
) -> dict:
    """Score the tags against the stored makes.

    Each stored make grades at most one tag, and each tag is graded by at most one
    stored make. Pairs are taken closest-first across the whole film rather than
    walking the tags in order: walking in order lets an early tagged miss swallow a
    stored make that sits right on top of a later tagged make, which would show up
    as both a miss called a make and a make missed from a single correct row.
    """
    ordered_tags = sorted(tags, key=lambda t: t["ms"])
    unused = [{"ms": m["ms"], "taken": False} for m in sorted(makes, key=lambda m: m["ms"])]

    pairs = sorted(
        ((abs(make["ms"] - tag["ms"]), ti, mi)
         for ti, tag in enumerate(ordered_tags)
         for mi, make in enumerate(unused)
         if abs(make["ms"] - tag["ms"]) <= tolerance_ms),
        key=lambda p: (p[0], p[1], p[2]),
    )
    matched: dict[int, tuple[int, int]] = {}
    for gap, ti, mi in pairs:
        if ti in matched or unused[mi]["taken"]:
            continue
        matched[ti] = (mi, gap)
        unused[mi]["taken"] = True

    buckets = {metric: [] for metric in METRICS}
    for ti, tag in enumerate(ordered_tags):
        hit = matched.get(ti)
        predicted_make = hit is not None
        if tag["made"] == predicted_make:
            bucket = "right"
        elif tag["made"]:
            bucket = "makes_missed"
        else:
            bucket = "misses_called_makes"
        buckets[bucket].append({
            **tag,
            "matched_ms": unused[hit[0]]["ms"] if hit else None,
            "gap_ms": hit[1] if hit else None,
        })

    result = {metric: len(buckets[metric]) for metric in METRICS}
    result["tags"] = len(tags)
    result["tagged_makes"] = sum(1 for t in tags if t["made"])
    result["tagged_misses"] = sum(1 for t in tags if not t["made"])
    result["stored_makes"] = len(makes)
    result["unmatched_stored_makes"] = sum(1 for m in unused if not m["taken"])
    result["detail"] = buckets
    return result


def regressions(result: dict, floor: dict) -> list[str]:
    """Why ``result`` is not allowed through, or an empty list.

    ``right`` may not fall and the two error counts may not rise. The floor is a
    floor on all three at once: trading six missed makes for six misses called
    makes keeps the total and still fails, because a miss called a make puts
    points on a card that were never scored.
    """
    problems = []
    if int(result.get("tags") or 0) != int(floor.get("tags") or 0):
        problems.append(
            f"tag count {result.get('tags')} != floor {floor.get('tags')}: "
            "the answer key changed, so the score is not comparable")
        return problems
    if result["right"] < int(floor["right"]):
        problems.append(f"right {result['right']} < floor {floor['right']}")
    for metric in ("makes_missed", "misses_called_makes"):
        if result[metric] > int(floor[metric]):
            problems.append(f"{metric} {result[metric]} > floor {floor[metric]}")
    return problems


def summary_line(result: dict) -> str:
    """The one line a report has to show. Anything shorter is not a result."""
    return (f"right={result['right']} makes_missed={result['makes_missed']} "
            f"misses_called_makes={result['misses_called_makes']} of {result['tags']} tags")
