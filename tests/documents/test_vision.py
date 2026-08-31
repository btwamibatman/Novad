from pathlib import Path

import pymupdf
import pytest

from app.services.documents import vision as document_vision
from app.services.ai.provider import AIGenerationResult
from app.services.ai import layout_review as ai_layout_review
from app.services.documents.vision import RenderedDocument, RenderedPage
from tests.helpers.pdf import make_pdf_with_text


def test_select_pages_for_layout_review_is_even_and_includes_edges():
    assert document_vision.select_pages_for_layout_review(1, 3) == [1]
    assert document_vision.select_pages_for_layout_review(10, 3) == [1, 5, 10]
    assert document_vision.select_pages_for_layout_review(10, 2) == [1, 10]


def test_render_pdf_for_layout_review_returns_ephemeral_png(tmp_path, monkeypatch):
    path = tmp_path / "document.pdf"
    path.write_bytes(make_pdf_with_text("Visible layout text for rendering."))
    monkeypatch.setattr(document_vision.settings, "layout_review_max_pages", 3)
    monkeypatch.setattr(document_vision.settings, "layout_review_dpi", 150)

    rendered = document_vision.render_pdf_for_layout_review(path)

    assert rendered.total_pages == 1
    assert rendered.dpi == 150
    assert rendered.pages[0].page_number == 1
    assert rendered.pages[0].data.startswith(b"\x89PNG")
    assert list(tmp_path.iterdir()) == [path]


def test_render_pdf_adapts_dpi_to_pixel_limit(tmp_path, monkeypatch):
    path = tmp_path / "oversized-scan.pdf"
    pdf = pymupdf.open()
    page = pdf.new_page(width=1717, height=2542)
    page.insert_text((100, 100), "Scanned document layout")
    pdf.save(path)
    pdf.close()
    monkeypatch.setattr(document_vision.settings, "layout_review_dpi", 150)
    monkeypatch.setattr(document_vision.settings, "layout_review_min_dpi", 72)
    monkeypatch.setattr(
        document_vision.settings,
        "layout_review_max_pixels_per_page",
        8_000_000,
    )

    rendered = document_vision.render_pdf_for_layout_review(path)
    image = pymupdf.Pixmap(rendered.pages[0].data)

    assert 72 <= rendered.dpi < 150
    assert image.width * image.height <= 8_000_000


def test_render_pdf_rejects_page_that_cannot_fit_at_minimum_dpi(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "huge.pdf"
    pdf = pymupdf.open()
    pdf.new_page(width=4000, height=4000)
    pdf.save(path)
    pdf.close()
    monkeypatch.setattr(document_vision.settings, "layout_review_dpi", 150)
    monkeypatch.setattr(document_vision.settings, "layout_review_min_dpi", 72)
    monkeypatch.setattr(
        document_vision.settings,
        "layout_review_max_pixels_per_page",
        8_000_000,
    )

    with pytest.raises(
        document_vision.DocumentVisionError,
        match="even at minimum DPI",
    ):
        document_vision.render_pdf_for_layout_review(path)


def test_layout_review_sends_images_without_content_analysis(monkeypatch, tmp_path):
    rendered = RenderedDocument(
        total_pages=4,
        dpi=150,
        pages=[
            RenderedPage(1, b"png-1", 210.0, 297.0),
            RenderedPage(4, b"png-4", 210.0, 297.0),
        ],
    )

    class FakeProvider:
        def generate_multimodal(self, prompt, images, **kwargs):
            assert "Не пересказывай" in prompt
            assert "№236" in prompt
            assert [image.data for image in images] == [b"png-1", b"png-4"]
            return AIGenerationResult("Layout is consistent.", "test-model")

    monkeypatch.setattr(
        ai_layout_review,
        "render_pdf_for_layout_review",
        lambda path: rendered,
    )
    monkeypatch.setattr(ai_layout_review, "get_ai_provider", lambda: FakeProvider())

    result = ai_layout_review.review_pdf_layout(Path(tmp_path / "unused.pdf"))

    assert result.text == "Layout is consistent."
    assert result.reviewed_pages == [1, 4]
    assert result.complete is False
