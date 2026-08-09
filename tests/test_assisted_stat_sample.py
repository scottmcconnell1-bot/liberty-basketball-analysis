"""SAMPLE / DELETE ME — assisted stating prototype route."""


def test_assisted_stat_sample_serves_banner(client):
    response = client.get("/film/assisted-stat-sample")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "SAMPLE / DELETE ME" in html
    assert "Quarter gate" in html
    assert "Accept" in html
    assert "Correct" in html
