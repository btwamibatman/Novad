def test_health_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "project": "Document Processing API",
    }


def test_untrusted_host_is_rejected(anonymous_client):
    response = anonymous_client.get(
        "/health",
        headers={"Host": "attacker.example"},
    )

    assert response.status_code == 400
    assert response.text == "Invalid host header"


def test_web_interface_returns_html(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Document Console" in response.text
    assert "loginForm" in response.text
    assert "logoutButton" in response.text
    assert "aiChatToggle" in response.text
    assert "aiChatDragHandle" in response.text
    assert "aiChatMaximize" in response.text
    assert "chat.privacy_notice" not in response.text
    assert "contentReviewButton" in response.text
    assert "layoutReviewButton" in response.text
    assert "PDF only" in response.text
    assert "/web/app.js" in response.text
