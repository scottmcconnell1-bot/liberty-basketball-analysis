"""Navigation cleanup tests for coach-facing Film & Stats and Teams menus."""


def test_film_stats_nav_shows_film_tool_and_videos_only(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.data.decode("utf-8")

    assert 'href="/film"' in html
    assert 'href="/videos"' in html
    assert "Film Tool" in html
    assert "Videos" in html
    assert 'href="/status"' not in html
    assert 'href="/review"' not in html
    assert "Review Queue" not in html


def test_teams_nav_hides_games_link(client):
    response = client.get("/")
    html = response.data.decode("utf-8")
    assert 'href="/games"' not in html
    assert 'href="/schedule"' in html


def test_games_page_redirects_to_schedule(client):
    response = client.get("/games")
    assert response.status_code == 302
    assert "/schedule" in response.headers["Location"]
