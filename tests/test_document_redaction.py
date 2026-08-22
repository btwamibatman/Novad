import pymupdf
import numpy as np
import pytest

from app.services import document_redaction, privacy_detection
from app.schemas.tools import RedactionPreviewRequest
from app.services.document_artifacts import _inspect_pdf
from app.services.document_redaction import (
    TextCandidate,
    RedactionError,
    _alpha,
    _barcode_findings,
    _resolve_text_overlaps,
    _visual_findings,
    apply_redactions,
    classify_kz_identifier,
    detect_redactions,
    find_text_candidates,
    validate_kz_identifier,
)


def test_pseudonym_labels_remain_distinct_after_twenty_six_values():
    assert [_alpha(index) for index in (1, 26, 27, 28, 52, 53)] == [
        "A",
        "Z",
        "AA",
        "AB",
        "AZ",
        "BA",
    ]


def _valid_identifier(first_eleven: str) -> str:
    assert len(first_eleven) == 11
    for checksum in range(10):
        candidate = f"{first_eleven}{checksum}"
        if validate_kz_identifier(candidate):
            return candidate
    raise AssertionError("Unable to create a valid synthetic identifier")


def test_balanced_redaction_default_includes_visual_privacy():
    request = RedactionPreviewRequest(document_id=1)

    assert request.categories == ["personal", "financial", "visual"]


def test_context_redaction_is_available_as_explicit_opt_in():
    request = RedactionPreviewRequest(document_id=1, categories=["context"])
    findings = find_text_candidates("Дата договора: 20.08.2026", {"context"})

    assert request.categories == ["context"]
    assert any(item.category == "DATE" for item in findings)


def test_person_requires_context_and_avoids_capitalized_document_phrases():
    text = (
        "Республика Казахстан\n"
        "Северный Казахстан\n"
        "Общие Положения\n"
        "Акционерное Общество\n"
        "ФИО: Иванов Иван Иванович\n"
        "Азамат: Әлиев Нұрлан Серікұлы"
    )

    findings = find_text_candidates(text, {"personal"})

    assert [item.text for item in findings if item.category == "PERSON"] == [
        "Иванов Иван Иванович",
        "Әлиев Нұрлан Серікұлы",
    ]


def test_person_does_not_treat_form_column_headers_as_a_name():
    text = "Фамилия Имя Отчество Категория Заявителя\nЛауазымы Азаматтарды қабылдау күні"

    assert not [item for item in find_text_candidates(text, {"personal"}) if item.category == "PERSON"]


def test_address_keeps_the_complete_comma_separated_value():
    text = "Адрес: г. Алматы, ул. Абая, д. 15, кв. 3\nТелефон: +7 700 111 22 33"

    findings = find_text_candidates(text, {"personal"})

    addresses = [item.text for item in findings if item.category == "ADDRESS"]
    assert addresses == ["г. Алматы, ул. Абая, д. 15, кв. 3"]


def test_unlabelled_kazakh_address_includes_city_street_and_building():
    text = "Астана қ., Есіл ауданы, Мәңгілік Ел даңғылы, 8, офис 4"

    findings = find_text_candidates(text, {"personal"})

    addresses = [item.text for item in findings if item.category == "ADDRESS"]
    assert addresses == [text]


def test_address_stops_before_the_next_organization_field():
    text = "г. Семей, ул. Абая, д. 8, ГУ «Аппарат маслихата области»"

    findings = find_text_candidates(text, {"personal", "service"})

    assert [(item.category, item.text) for item in findings] == [
        ("ADDRESS", "г. Семей, ул. Абая, д. 8"),
        ("ORG", "ГУ «Аппарат маслихата области»"),
    ]


def test_bare_identifiers_require_checksum_and_use_current_bin_structure():
    synthetic_iin = _valid_identifier("90010130000")
    synthetic_bin = _valid_identifier("24014000000")
    invalid = synthetic_iin[:-1] + str((int(synthetic_iin[-1]) + 1) % 10)

    assert classify_kz_identifier(synthetic_iin) == "IIN"
    assert classify_kz_identifier(synthetic_bin) == "BIN"
    assert classify_kz_identifier(invalid) is None

    personal = find_text_candidates(f"Заявитель {synthetic_iin}; код {invalid}", {"personal"})
    service = find_text_candidates(f"Компания {synthetic_bin}; код {invalid}", {"service"})

    assert [(item.category, item.text) for item in personal] == [("IIN", synthetic_iin)]
    assert [(item.category, item.text) for item in service] == [("BIN", synthetic_bin)]


def test_bare_identifier_does_not_consume_cadastral_or_spaced_numbers():
    text = "Кадастровый номер 21-320-109-1207, значение 292 266 237 221"

    assert not [
        item
        for item in find_text_candidates(text, {"personal", "service"})
        if item.category in {"IIN", "BIN", "IIN_OR_BIN"}
    ]


def test_explicit_identifier_label_is_kept_even_when_ocr_breaks_checksum():
    findings = find_text_candidates("ИИН: 123456789012", {"personal"})

    assert [(item.category, item.text, item.confidence) for item in findings] == [
        ("IIN", "123456789012", 0.86)
    ]


def test_service_terms_cover_ru_and_kk_forms_without_masking_generic_nouns():
    text = (
        "ТОО «Альфа»\n"
        "ЖШС «Бета»\n"
        "Алматы қаласының әкімдігі\n"
        "Акимат города Астаны\n"
        "Прокуратура проверила материалы, суд рассмотрел дело, нотариус выдал документ."
    )

    findings = find_text_candidates(text, {"service"})
    organizations = [item.text for item in findings if item.category == "ORG"]

    assert organizations == [
        "ТОО «Альфа»",
        "ЖШС «Бета»",
        "Алматы қаласының әкімдігі",
        "Акимат города Астаны",
    ]


def test_kazakh_common_word_and_document_words_are_not_service_entities():
    text = "ақ өңірлік даму, активность выросла, счет собственных средств"

    findings = find_text_candidates(text, {"service"})

    assert not [item for item in findings if item.category in {"ORG", "DOC_ID"}]


def test_email_label_does_not_duplicate_email_as_a_postal_address():
    findings = find_text_candidates("Электронный адрес: user@example.com", {"personal"})

    assert [(item.category, item.text) for item in findings] == [("EMAIL", "user@example.com")]


def test_overlap_resolution_reserves_range_for_higher_priority_entity():
    candidates = [
        TextCandidate("personal", "PERSON", "города Алматы", 7, 21, 0.88, 60),
        TextCandidate("service", "ORG", "Акимат города Алматы", 0, 21, 0.86, 70),
    ]

    assert _resolve_text_overlaps(candidates) == [candidates[1]]


def test_amount_pattern_matches_currency_symbols_without_word_boundary():
    findings = find_text_candidates("Суммы: 5 000 ₸, 250 € и 99 USD.", {"financial"})

    assert [item.text for item in findings if item.category == "AMOUNT"] == [
        "5 000 ₸",
        "250 €",
        "99 USD",
    ]


def test_mixed_page_runs_ocr_even_when_native_footer_exists(tmp_path, monkeypatch):
    source = tmp_path / "mixed.pdf"
    image_document = pymupdf.open()
    image_page = image_document.new_page(width=400, height=300)
    image_page.insert_text((30, 80), "scan@example.kz", fontsize=24)
    image = image_page.get_pixmap(alpha=False).tobytes("png")
    image_document.close()

    document = pymupdf.open()
    page = document.new_page()
    page.insert_image(pymupdf.Rect(40, 40, 500, 500), stream=image)
    page.insert_text((72, 760), "Native footer")
    document.save(source)
    document.close()

    ocr_text = "scan@example.kz"
    monkeypatch.setattr(
        document_redaction,
        "_ocr_page_words",
        lambda page: (
            [
                {
                    "start": 0,
                    "end": len(ocr_text),
                    "rect": pymupdf.Rect(80, 100, 250, 130),
                    "confidence": 91,
                }
            ],
            ocr_text,
            91.0,
        ),
    )

    class EmptyDocument:
        ents = []

    monkeypatch.setattr(
        privacy_detection,
        "_stanza_pipeline",
        lambda language, model_dir: lambda text: EmptyDocument(),
    )

    findings, meta = detect_redactions(source, {"personal"})

    assert [(item["category"], item["text"], item["source"]) for item in findings] == [
        ("EMAIL", "scan@example.kz", "ocr")
    ]
    assert meta["native_text_page_count"] == 1
    assert meta["ocr_page_count"] == 1
    assert meta["coverage"]["complete"] is True
    assert meta["coverage"]["pages"][0]["ocr_required"] is True


def test_mixed_page_ocr_failure_is_visible_in_coverage(tmp_path, monkeypatch):
    source = tmp_path / "mixed-failure.pdf"
    image_document = pymupdf.open()
    image_page = image_document.new_page(width=100, height=100)
    image_page.insert_text((10, 40), "private")
    image = image_page.get_pixmap(alpha=False).tobytes("png")
    image_document.close()

    document = pymupdf.open()
    page = document.new_page()
    page.insert_image(pymupdf.Rect(0, 0, 400, 400), stream=image)
    page.insert_text((72, 760), "Native footer")
    document.save(source)
    document.close()

    def failed_ocr(page):
        raise RuntimeError("Tesseract is unavailable")

    monkeypatch.setattr(document_redaction, "_ocr_page_words", failed_ocr)

    class EmptyDocument:
        ents = []

    monkeypatch.setattr(
        privacy_detection,
        "_stanza_pipeline",
        lambda language, model_dir: lambda text: EmptyDocument(),
    )

    _, meta = detect_redactions(source, {"personal"})

    assert meta["coverage"]["complete"] is False
    assert meta["coverage"]["unchecked_pages"] == [1]
    assert meta["coverage"]["pages"][0]["ocr_status"] == "failed"
    assert any(item["detector"] == "ocr" for item in meta["detector_failures"])


def test_empty_ocr_on_non_empty_page_is_not_treated_as_complete(tmp_path, monkeypatch):
    source = tmp_path / "unreadable.pdf"
    document = pymupdf.open()
    document.new_page().insert_text((72, 72), "PII")
    document.save(source)
    document.close()

    monkeypatch.setattr(
        document_redaction,
        "_ocr_page_words",
        lambda _page: ([], "", None),
    )

    class EmptyDocument:
        ents = []

    monkeypatch.setattr(
        privacy_detection,
        "_stanza_pipeline",
        lambda language, model_dir: lambda text: EmptyDocument(),
    )

    _, meta = detect_redactions(source, {"personal"})

    assert meta["coverage"]["complete"] is False
    assert meta["coverage"]["unchecked_pages"] == [1]
    assert meta["coverage"]["pages"][0]["ocr_status"] == "failed"
    assert any(
        item["detector"] == "ocr"
        and "no readable text" in item["message"]
        for item in meta["detector_failures"]
    )


def test_apply_removes_annotations_widgets_and_bookmarks(tmp_path):
    source = tmp_path / "interactive.pdf"
    destination = tmp_path / "protected.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "secret@example.com")
    annotation = page.add_text_annot((100, 100), "note-secret@example.com")
    annotation.set_info(
        title="author-secret@example.com",
        content="note-secret@example.com",
    )
    widget = pymupdf.Widget()
    widget.field_name = "field-secret"
    widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
    widget.field_value = "widget-secret@example.com"
    widget.rect = pymupdf.Rect(72, 120, 250, 145)
    page.add_widget(widget)
    document.set_toc([[1, "bookmark-secret@example.com", 1]])
    document.save(source)
    document.close()

    finding = {
        "id": "finding-1",
        "page": 1,
        "pdf_rect": [70, 55, 260, 82],
        "category": "EMAIL",
        "text": "secret@example.com",
    }

    apply_redactions(
        source,
        destination,
        [finding],
        {"finding-1"},
        "black",
    )

    with pymupdf.open(destination) as protected:
        assert protected.get_toc() == []
        assert list(protected[0].annots() or []) == []
        assert list(protected[0].widgets() or []) == []
    payload = destination.read_bytes()
    assert b"note-secret" not in payload
    assert b"widget-secret" not in payload
    assert b"bookmark-secret" not in payload


def test_apply_flattens_every_page_and_drops_unknown_catalog_objects(tmp_path):
    source = tmp_path / "catalog-secret.pdf"
    destination = tmp_path / "protected.pdf"
    document = pymupdf.open()
    first_page = document.new_page(width=612, height=792)
    first_page.insert_text((72, 72), "visible@example.com")
    document.new_page(width=420, height=595).insert_text((72, 72), "Public page")
    document.xref_set_key(
        document.pdf_catalog(),
        "PrivateNote",
        "(hidden-secret@example.com)",
    )
    source_sizes = [
        (round(page.rect.width, 2), round(page.rect.height, 2))
        for page in document
    ]
    document.save(source)
    document.close()

    finding = {
        "id": "finding-1",
        "page": 1,
        "pdf_rect": [65, 50, 260, 85],
        "category": "EMAIL",
        "text": "visible@example.com",
    }

    meta = apply_redactions(
        source,
        destination,
        [finding],
        {"finding-1"},
        "black",
    )

    assert meta["flattened"] is True
    assert meta["selectable_text"] is False
    with pymupdf.open(destination) as protected:
        assert protected.page_count == 2
        assert [
            (round(page.rect.width, 2), round(page.rect.height, 2))
            for page in protected
        ] == source_sizes
        assert protected.xref_get_key(
            protected.pdf_catalog(), "PrivateNote"
        )[0] == "null"
        assert all(not page.get_text().strip() for page in protected)

    payload = destination.read_bytes()
    assert b"PrivateNote" not in payload
    assert b"hidden-secret@example.com" not in payload
    structure, coverage, _ = _inspect_pdf(destination, None)
    assert structure["unsafe_item_count"] == 0
    assert coverage["verification_completed"] is True


def test_apply_fails_closed_when_flattened_pdf_cannot_fit_ai_limit(
    tmp_path,
    monkeypatch,
):
    source = tmp_path / "source.pdf"
    destination = tmp_path / "protected.pdf"
    document = pymupdf.open()
    document.new_page().insert_text((72, 72), "visible@example.com")
    document.save(source)
    document.close()
    monkeypatch.setattr(document_redaction.settings, "ai_max_pdf_bytes", 1)

    with pytest.raises(RedactionError, match="AI upload limit"):
        apply_redactions(
            source,
            destination,
            [
                {
                    "id": "finding-1",
                    "page": 1,
                    "pdf_rect": [65, 50, 260, 85],
                    "category": "EMAIL",
                    "text": "visible@example.com",
                }
            ],
            {"finding-1"},
            "black",
        )

    assert not destination.exists()


def test_visual_detection_finds_qr_code_and_marks_it_for_review():
    import cv2

    qr = cv2.QRCodeEncoder_create().encode("secret@example.com")
    encoded, payload = cv2.imencode(".png", qr)
    assert encoded is True
    document = pymupdf.open()
    page = document.new_page()
    page.insert_image(pymupdf.Rect(72, 72, 300, 300), stream=payload.tobytes())

    findings, failures, detectors = _visual_findings(page, 1)

    document.close()
    qr_findings = [item for item in findings if item["category"] == "QR_CODE"]
    assert len(qr_findings) == 1
    assert qr_findings[0]["review_required"] is True
    assert failures == []
    assert {"opencv-qr", "opencv-barcode"} <= set(detectors)


def test_barcode_detector_coordinates_use_visual_taxonomy():
    class FakeBarcodeDetector:
        def detectMulti(self, image):
            return True, np.array([[[10, 20], [110, 20], [110, 60], [10, 60]]])

    class FakeCV2:
        barcode_BarcodeDetector = FakeBarcodeDetector

    document = pymupdf.open()
    page = document.new_page()
    findings = _barcode_findings(
        FakeCV2,
        page,
        1,
        np.zeros((100, 150, 3), dtype=np.uint8),
        1.0,
    )
    document.close()

    assert len(findings) == 1
    assert findings[0]["category"] == "BARCODE"
    assert findings[0]["group"] == "visual"
    assert findings[0]["review_required"] is True


def test_visual_subdetector_failure_marks_page_coverage_incomplete(
    tmp_path,
    monkeypatch,
):
    source = tmp_path / "visual-failure.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Enough native text to avoid an OCR-only fallback on this page.")
    document.save(source)
    document.close()

    def failed_barcode(*args, **kwargs):
        raise RuntimeError("Barcode detector failed")

    monkeypatch.setattr(document_redaction, "_barcode_findings", failed_barcode)

    _, meta = detect_redactions(source, {"visual"})

    assert meta["coverage"]["complete"] is False
    assert meta["coverage"]["pages"][0]["visual_status"] == "partial"
    assert any(
        item["detector"] == "opencv-barcode"
        for item in meta["detector_failures"]
    )
