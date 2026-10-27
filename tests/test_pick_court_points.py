import numpy as np

import pick_court_points as picker


COURT_TO_IMAGE = np.array([
    [14.0, -6.0, 640.0],
    [1.5, -5.0, 520.0],
    [0.002, -0.006, 1.0],
], dtype=np.float64)


def _to_image(x_ft, y_ft):
    u, v, w = COURT_TO_IMAGE @ np.array([x_ft, y_ft, 1.0])
    return [u / w, v / w]


def _clicks(half_court_y):
    points = [{"name": n, "image_xy": _to_image(*xy)} for n, xy in picker.LANE_COURT_XY.items()]
    points.append({"name": "halfcourt_a", "image_xy": _to_image(-20.0, half_court_y)})
    points.append({"name": "halfcourt_b", "image_xy": _to_image(18.0, half_court_y)})
    return points


def test_half_court_clicks_report_the_gym_length(capsys):
    picker.report_half_court(_clicks(36.75))  # 84 ft court
    out = capsys.readouterr().out
    assert "Half court is 36.75 ft from the hoop" in out
    assert "84.0 ft court" in out


def test_a_bad_half_court_click_is_reported_not_used(capsys):
    picker.report_half_court(_clicks(13.75))  # clicked the free-throw line by mistake
    assert "[WARN]" in capsys.readouterr().out


def test_half_court_labels_do_not_reuse_lane_labels():
    assert not set(picker.HALFCOURT_KEYPOINTS) & set(picker.DEFAULT_KEYPOINTS)
