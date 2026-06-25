def test_review_page_renders_required_controls(client):
    response = client.get("/review")

    assert response.status_code == 200
    assert b"Review Queue" in response.data
    assert b"filter-review-status" in response.data
    assert b"review-events-table" in response.data
    assert b"review-detail-form" in response.data
    assert b"review-accept" in response.data
    assert b"review-correct" in response.data
    assert b"review-reject" in response.data
    assert b"/api/review/events" in response.data


def test_review_queue_navigation_visible_when_manual_tagging_enabled(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b'href="/review"' in response.data
    assert b"Review Queue" in response.data


def test_review_page_hidden_when_manual_tagging_disabled(app, client):
    original = app.config["FEATURES"]["ENABLE_MANUAL_TAG_MVP"]
    app.config["FEATURES"]["ENABLE_MANUAL_TAG_MVP"] = False
    try:
        response = client.get("/review")
        assert response.status_code == 404
    finally:
        app.config["FEATURES"]["ENABLE_MANUAL_TAG_MVP"] = original
