from jersey_shade import shade_from_value, side_from_shade, side_label


def test_home_is_light_away_is_dark():
    assert shade_from_value(200) == "light"
    assert shade_from_value(40) == "dark"
    from jersey_shade import shade_from_hsv
    assert shade_from_hsv(20, 200) == "light"
    assert shade_from_hsv(140, 90) == "dark"
    assert side_from_shade("light") == "home"
    assert side_from_shade("dark") == "away"
    assert side_label("home") == "Home (light)"
    assert side_label("away") == "Away (dark)"
