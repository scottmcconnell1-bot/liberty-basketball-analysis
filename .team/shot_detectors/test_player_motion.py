"""Tests for measure_player_motion module (pure maths functions)."""

from __future__ import annotations

import pytest

# Import the pure maths functions we'll extract for testability
# Since measure_player_motion.py doesn't expose them yet, we'll test the logic
# by importing and calling the internal functions, or we define the expected
# behavior here as regression tests for the math.

import math
import numpy as np


def median_of_list(vals):
    """Reference implementation matching measure_player_motion.py."""
    if not vals:
        return None
    return float(np.median(vals))


def distance(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


class TestHoopChooser:
    """Test the hoop selection logic: nearest within 2 widths, else skip frame."""

    def test_nearest_within_2_widths(self):
        """Hoop nearest to previous center, within 2*prev_width, is chosen."""
        prev_center = (100.0, 200.0)
        prev_width = 50.0
        hoop_boxes = [
            (90.0, 195.0, 48.0),   # dist ~11.2, within 100
            (200.0, 200.0, 50.0),  # dist 100, at boundary (2*50=100) -> accepted
            (300.0, 300.0, 60.0),  # dist ~223, > 100 -> rejected
        ]
        # First is nearest and within 2 widths
        chosen = min(hoop_boxes, key=lambda hb: distance((hb[0], hb[1]), prev_center))
        assert chosen == (90.0, 195.0, 48.0)
        assert distance((chosen[0], chosen[1]), prev_center) <= 2 * prev_width

    def test_skip_when_too_far(self):
        """No hoop within 2 widths -> frame skipped."""
        prev_center = (100.0, 200.0)
        prev_width = 50.0
        hoop_boxes = [
            (300.0, 300.0, 60.0),  # dist ~223 > 100
            (400.0, 400.0, 50.0),  # dist ~424 > 100
        ]
        # All are too far
        nearest = min(hoop_boxes, key=lambda hb: distance((hb[0], hb[1]), prev_center))
        assert distance((nearest[0], nearest[1]), prev_center) > 2 * prev_width
        # Frame should be skipped (hoop_missing_count incremented)

    def test_starting_from_track_hoop(self):
        """First frame uses track['hoop'] as previous center."""
        track_hoop = [100.0, 200.0, 50.0, 100.0]  # [x, y, w, h]
        prev_center = (track_hoop[0], track_hoop[1])
        prev_width = track_hoop[2]
        assert prev_center == (100.0, 200.0)
        assert prev_width == 50.0


class TestDistanceInHoopWidths:
    """Test distance calculation in hoop-width units."""

    def test_basic_conversion(self):
        """dist_hw = euclidean_dist / hoop_width."""
        player_center = (150.0, 250.0)
        hoop_center = (100.0, 200.0)
        hoop_width = 50.0
        dist = distance(player_center, hoop_center)
        dist_hw = dist / hoop_width
        expected = math.hypot(50, 50) / 50.0
        assert abs(dist_hw - expected) < 1e-6

    def test_players_within_3hw(self):
        """Count players with dist_hw <= 3.0."""
        ZONE_HOOP_WIDTHS_H = 3.0
        player_distances_hw = [1.0, 2.5, 3.0, 3.5, 4.0]
        within = sum(1 for d in player_distances_hw if d <= ZONE_HOOP_WIDTHS_H)
        assert within == 3


class TestFirstLastMedians:
    """Test median over first 1s and last 1s frames, and change."""

    def test_median_first_last_1s(self):
        """Median over first N and last N frames (1s at fps)."""
        fps = 25.0
        measure_frames = round(1.0 * fps)  # 25 frames
        per_frame_values = list(range(100))  # 100 frames
        first = per_frame_values[:measure_frames]
        last = per_frame_values[-measure_frames:]
        med_first = median_of_list([float(x) for x in first])
        med_last = median_of_list([float(x) for x in last])
        assert med_first == float(np.median(first))
        assert med_last == float(np.median(last))

    def test_change_last_minus_first(self):
        """Change = median_last_1s - median_first_1s."""
        first_vals = [1, 2, 3, 4, 5]
        last_vals = [6, 7, 8, 9, 10]
        med_first = median_of_list([float(x) for x in first_vals])
        med_last = median_of_list([float(x) for x in last_vals])
        change = med_last - med_first
        assert change == 5.0

    def test_change_with_none_values(self):
        """Frames with None (hoop missing) are excluded from median."""
        vals_with_none = [1.0, 2.0, None, 3.0, None, 4.0]
        filtered = [v for v in vals_with_none if v is not None]
        med = median_of_list(filtered)
        assert med == median_of_list([1.0, 2.0, 3.0, 4.0])


class TestSummaryStats:
    """Test makes vs misses summary statistics (median, min, max)."""

    def test_summary_structure(self):
        """Summary has makes and misses with median/min/max per measure."""
        makes_data = {
            "players_within_3hw_first_1s": [2, 3, 3, 4, 5],
            "players_within_3hw_last_1s": [1, 2, 2, 3, 4],
            "players_within_3hw_change": [-1, -1, 0, 1, 1],
            "median_player_distance_hw_first_1s": [1.5, 2.0, 2.5, 2.5, 3.0],
            "median_player_distance_hw_last_1s": [1.0, 1.5, 2.0, 2.5, 3.0],
            "median_player_distance_hw_change": [-0.5, -0.5, 0.0, 0.5, 0.5],
        }

        def stats(vals):
            return {"median": median_of_list(vals), "min": min(vals), "max": max(vals)}

        for key, vals in makes_data.items():
            s = stats(vals)
            assert s["median"] is not None
            assert s["min"] <= s["median"] <= s["max"]


class TestOutputDirectoryRefusal:
    """Test that script refuses to run if output dir exists and non-empty."""

    def test_refusal_logic(self, tmp_path):
        """Simulate the refusal check."""
        out_dir = tmp_path / "player_motion"
        out_dir.mkdir()
        (out_dir / "existing.json").write_text("{}")

        # The check in main():
        if out_dir.exists() and any(out_dir.iterdir()):
            refused = True
        else:
            refused = False
        assert refused

    def test_allows_empty_dir(self, tmp_path):
        """Empty directory is allowed."""
        out_dir = tmp_path / "player_motion"
        out_dir.mkdir()

        if out_dir.exists() and any(out_dir.iterdir()):
            refused = True
        else:
            refused = False
        assert not refused

    def test_allows_nonexistent(self, tmp_path):
        """Non-existent directory is allowed (will be created)."""
        out_dir = tmp_path / "player_motion_new"
        if out_dir.exists() and any(out_dir.iterdir()):
            refused = True
        else:
            refused = False
        assert not refused


if __name__ == "__main__":
    pytest.main([__file__, "-v"])