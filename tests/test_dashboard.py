def test_dashboard_summary_returns_document_metrics(client):
    first = client.post(
        "/api/documents/upload",
        files={
            "file": (
                "contract.txt",
                b"This contract text is long enough to detect English language.",
                "text/plain",
            )
        },
    )
    assert first.status_code == 201
    client.post(f"/api/documents/{first.json()['id']}/analyze")

    second = client.post(
        "/api/documents/upload",
        files={"file": ("blank.txt", b"   ", "text/plain")},
    )
    assert second.status_code == 201
    client.post(f"/api/documents/{second.json()['id']}/analyze")

    response = client.get("/api/dashboard/summary")

    assert response.status_code == 200
    data = response.json()
    assert data["total_documents"] == 2
    assert data["processed_documents"] == 1
    assert data["failed_documents"] == 1
    assert data["storage_bytes"] > 0
    assert data["detected_languages"]["en"] == 1
