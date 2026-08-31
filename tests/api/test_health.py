from app import main as main_module


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


def test_web_interface_returns_vue_entrypoint(client, monkeypatch, tmp_path):
    index_path = tmp_path / "index.html"
    index_path.write_text(
        (
            '<!doctype html><html><head><title>Document Console</title></head>'
            '<body><div id="app"></div>'
            '<script type="module" src="/web/dist/assets/index-test.js"></script>'
            "</body></html>"
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(main_module, "WEB_INDEX", index_path)

    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Document Console" in response.text
    assert '<div id="app"></div>' in response.text
    assert 'type="module"' in response.text
    assert "/web/dist/assets/" in response.text
    assert "/web/app.js" not in response.text


def test_web_interface_reports_missing_frontend_build(
    anonymous_client,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(main_module, "WEB_INDEX", tmp_path / "missing-index.html")

    response = anonymous_client.get("/")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Frontend build is unavailable; run npm run build in frontend/"
    }
