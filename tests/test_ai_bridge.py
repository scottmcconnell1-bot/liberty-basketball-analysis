import numpy as np
import pytest

import ai_bridge
from court_homography import CourtReferencePoint, compute_homography


# A fixed sideline-camera perspective (court feet -> image pixels) used to fake
# clicked points. The test recovers the homography from four lane points only,
# the same way manual_calibration.json is used.
COURT_TO_IMAGE = np.array([
    [14.0, -6.0, 640.0],
    [1.5, -5.0, 520.0],
    [0.002, -0.006, 1.0],
], dtype=np.float64)


def _to_image(x_ft, y_ft):
    u, v, w = COURT_TO_IMAGE @ np.array([x_ft, y_ft, 1.0])
    return (u / w, v / w)


def _lane_homography():
    # Hoop-origin feet: free-throw line 13.75 ft out, baseline 5.25 ft behind, lane 12 ft wide.
    court = {
        'ft_line_left': (-6.0, 13.75),
        'ft_line_right': (6.0, 13.75),
        'baseline_left': (-6.0, -5.25),
        'baseline_right': (6.0, -5.25),
    }
    refs = [CourtReferencePoint(name, xy, _to_image(*xy), 1.0) for name, xy in court.items()]
    return compute_homography(refs)


@pytest.mark.parametrize('court_length_ft', [74.0, 84.0, 94.0])
def test_half_court_is_measured_from_the_lane_points_for_any_gym_length(court_length_ft):
    H = _lane_homography()
    true_half_court = court_length_ft / 2.0 - 5.25
    clicks = [_to_image(-20.0, true_half_court), _to_image(15.0, true_half_court)]

    measured = ai_bridge.half_court_y_from_image_points(H, clicks)

    assert measured == pytest.approx(true_half_court, abs=0.05)


def test_an_implausible_half_court_click_is_ignored():
    H = _lane_homography()
    assert ai_bridge.half_court_y_from_image_points(H, [_to_image(0.0, 13.75)]) is None
    assert ai_bridge.half_court_y_from_image_points(H, []) is None
    assert ai_bridge.half_court_y_from_image_points(None, [(1.0, 1.0)]) is None


def test_half_court_source_order():
    assert ai_bridge.resolve_half_court_limit(None) == (41.75, 'default_94ft')
    assert ai_bridge.resolve_half_court_limit({'court_length_ft': 84.0}) == (36.75, 'court_length')
    assert ai_bridge.resolve_half_court_limit(
        {'court_length_ft': 84.0, 'half_court_y_ft': 33.0}) == (33.0, 'measured')


def test_liberty_gym_is_92_ft_and_unknown_gyms_use_the_default():
    liberty = ai_bridge.court_config_for_gym('Liberty')
    assert ai_bridge.resolve_half_court_limit(liberty) == (40.75, 'court_length')
    assert ai_bridge.classify_court_zone(0, 41.0, config=liberty) == 'transition'
    assert ai_bridge.court_config_for_gym('Adrian') == {}
    assert ai_bridge.resolve_half_court_limit(ai_bridge.court_config_for_gym(None))[1] == 'default_94ft'


def test_zones_are_unchanged_without_gym_config():
    zone = ai_bridge.classify_court_zone
    assert zone(0, 2) == 'rim'
    assert zone(10, -1) == 'backcourt'
    assert zone(0, 10) == 'paint'
    assert zone(15, 10) == 'perimeter'
    assert zone(0, 30) == 'three'
    assert zone(0, 41.0) == 'three'
    assert zone(0, 42.5) == 'transition'


def test_a_measured_half_court_moves_transition_on_a_short_court():
    zone = ai_bridge.classify_court_zone
    short_gym = {'half_court_y_ft': 31.75}  # 74 ft court
    assert zone(0, 33.0) == 'three'
    assert zone(0, 33.0, config=short_gym) == 'transition'
    assert zone(0, 30.0, config=short_gym) == 'three'
