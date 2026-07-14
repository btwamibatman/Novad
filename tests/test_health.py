def test_health_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "project": "Document Processing API",
    }


def test_web_interface_returns_html(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Document Console" in response.text
    assert "aiChatToggle" in response.text
    assert "contentReviewButton" in response.text
    assert "layoutReviewButton" in response.text
    assert "PDF only" in response.text
    assert "/web/app.js" in response.text
