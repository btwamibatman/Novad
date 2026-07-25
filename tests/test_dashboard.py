from tests.pdf_helpers import make_pdf_with_text


def test_dashboard_summary_returns_document_metrics(
    client, other_client, monkeypatch, analysis_runner
):
    first = client.post(
        "/api/documents/upload",
        files={
            "file": (
                "contract.pdf",
                make_pdf_with_text(
                    "This contract text is long enough to detect English language."
                ),
                "application/pdf",
            )
        },
    )
    assert first.status_code == 201
    client.post(f"/api/documents/{first.json()['id']}/analyze")
    analysis_runner()

    second = client.post(
        "/api/documents/upload",
        files={
            "file": (
                "broken.pdf",
                make_pdf_with_text("This valid PDF will simulate an analysis failure."),
                "application/pdf",
            )
        },
    )
    assert second.status_code == 201

    def fail_extraction(document, progress_callback=None):
        raise ValueError("Simulated analysis failure")

    with monkeypatch.context() as patch:
        patch.setattr(
            "app.services.analysis_jobs.extract_text_pages",
            fail_extraction,
        )
        client.post(f"/api/documents/{second.json()['id']}/analyze")
        analysis_runner()

    other = other_client.post(
        "/api/documents/upload",
        files={
            "file": (
                "other-session.pdf",
                make_pdf_with_text(
                    "This other session document should not be counted here."
                ),
                "application/pdf",
            )
        },
    )
    assert other.status_code == 201
    other_client.post(f"/api/documents/{other.json()['id']}/analyze")
    analysis_runner()

    response = client.get("/api/dashboard/summary")

    assert response.status_code == 200
    data = response.json()
    assert data["total_documents"] == 2
    assert data["processed_documents"] == 1
    assert data["failed_documents"] == 1
    assert data["storage_bytes"] > 0
    assert data["detected_languages"]["en"] == 1

    other_response = other_client.get("/api/dashboard/summary")
    assert other_response.status_code == 200
    assert other_response.json()["total_documents"] == 1
