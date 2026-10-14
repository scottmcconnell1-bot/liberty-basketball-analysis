"""Red score digits on the Adrian NFHS board, read from board crops of the real film."""

from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

import scoreboard_clock as sc

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "scoreboard"

# Video second -> (mustangs, guest, period), checked by eye on the film.
# Period 3 does not read on this board yet; it must stay None, never a wrong quarter.
GROUND_TRUTH = {
    122: (0, 6, 1),
    1200: (10, 17, 2),
    1800: (15, 24, 2),
    3000: (21, 43, None),
    3500: (24, 46, 4),
    3850: (26, 51, 4),
}


def _frame(second: int) -> np.ndarray:
    board = cv2.imread(str(FIXTURES / f"adrian_board_{second}.png"))
    assert board is not None, second
    x0, y0, x1, y1 = sc._BOARD
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[y0:y1, x0:x1] = board
    return frame


@pytest.mark.parametrize("second", sorted(GROUND_TRUTH))
def test_board_scores_match_the_film(second):
    mustangs, guest, period = GROUND_TRUTH[second]
    read = sc.read_scoreboard(_frame(second))
    assert (read["mustangs"], read["guest"]) == (mustangs, guest), read["raw"]
    assert read["period"] == period, read["raw"]


def test_read_scoreboard_keeps_its_keys():
    read = sc.read_scoreboard(_frame(3500))
    assert set(read) == {
        "clock", "period", "mustangs", "guest", "mustangs_fouls", "guest_fouls",
        "foul_jersey", "foul_count", "raw",
    }


def test_a_score_that_is_not_fully_read_is_none():
    assert sc._score_value(["8"]) == 8
    assert sc._score_value(["46"]) == 46
    assert sc._score_value(["05"]) is None
    assert sc._score_value(["?3"]) is None
    assert sc._score_value(["4?"]) is None
    assert sc._score_value([]) is None


def test_a_dark_ones_slot_under_a_lit_tens_is_not_a_one_digit_score(monkeypatch):
    reads = iter(["2", ""])
    monkeypatch.setattr(sc, "_slot_digit", lambda mask, slot: next(reads))
    groups = sc._score_text(_frame(3500)[840:1030, 1535:1880], sc._CELLS["home_score"])
    assert sc._score_value(groups) is None, groups
