import numpy

from app.services import text_analysis
from app.services.text_analysis import (
    DetectedCell,
    DetectedTable,
    OCRCandidate,
    OCRWord,
)


def _word(text: str, confidence: float, left: int, top: int) -> OCRWord:
    return OCRWord(
        text=text,
        confidence=confidence,
        left=left,
        top=top,
        width=40,
        height=15,
        block=1,
        paragraph=1,
        line=1,
    )


def test_table_words_are_assigned_to_their_cells_without_crossing_rows():
    table = DetectedTable(
        left=0,
        top=0,
        right=200,
        bottom=100,
        rows=2,
        columns=2,
        cells=[
            DetectedCell(0, 0, 0, 0, 100, 50),
            DetectedCell(0, 1, 100, 0, 200, 50),
            DetectedCell(1, 0, 0, 50, 100, 100),
            DetectedCell(1, 1, 100, 50, 200, 100),
        ],
    )
    words = (
        _word("Contract-A", 95, 10, 10),
        _word("100-KZT", 94, 120, 10),
        _word("Contract-B", 96, 10, 65),
        _word("200-KZT", 93, 120, 65),
    )

    text_analysis._assign_words_to_tables([table], words)
    markdown = text_analysis._markdown_table(table)

    assert "| Contract-A | 100-KZT |" in markdown
    assert "| Contract-B | 200-KZT |" in markdown
    assert "Contract-A | 200-KZT" not in markdown


def test_detect_tables_finds_a_clear_ruled_grid():
    cv2, _ = text_analysis._cv2_and_numpy()
    image = numpy.full((500, 700), 255, dtype=numpy.uint8)
    for y in (100, 200, 300, 400):
        cv2.line(image, (50, y), (650, y), 0, 4)
    for x in (50, 250, 450, 650):
        cv2.line(image, (x, 100), (x, 400), 0, 4)

    tables = text_analysis._detect_tables(image)

    assert len(tables) == 1
    assert tables[0].rows == 3
    assert tables[0].columns == 3
    assert len(tables[0].cells) == 9
    assert tables[0].ambiguous is False


def test_detect_tables_supports_a_simple_merged_header_cell():
    cv2, _ = text_analysis._cv2_and_numpy()
    image = numpy.full((500, 700), 255, dtype=numpy.uint8)
    for y in (100, 200, 300, 400):
        cv2.line(image, (50, y), (650, y), 0, 4)
    for x in (50, 450, 650):
        cv2.line(image, (x, 100), (x, 400), 0, 4)
    cv2.line(image, (250, 200), (250, 400), 0, 4)

    tables = text_analysis._detect_tables(image)

    assert len(tables) == 1
    merged = next(
        cell
        for cell in tables[0].cells
        if cell.row == 0 and cell.column == 0
    )
    assert merged.column_span == 2
    assert tables[0].ambiguous is False


def test_markdown_marks_an_uncertain_cell_instead_of_guessing():
    cell = DetectedCell(
        0,
        0,
        0,
        0,
        100,
        50,
        words=[_word("4521-K", 42, 10, 10)],
        uncertain=True,
    )
    table = DetectedTable(0, 0, 100, 50, 1, 1, [cell])

    assert "4521-K [UNCERTAIN_OCR]" in text_analysis._markdown_table(table)


def test_candidate_score_penalizes_low_confidence_words():
    clean = OCRCandidate(
        text="Clean readable document text",
        words=(),
        mean_confidence=88,
        low_confidence_ratio=0.05,
        preprocessing="contrast",
    )
    noisy = OCRCandidate(
        text="Noisy document text",
        words=(),
        mean_confidence=90,
        low_confidence_ratio=0.40,
        preprocessing="threshold",
    )

    assert clean.score > noisy.score


def test_native_text_gate_rejects_corrupted_text_layers():
    assert text_analysis._native_text_is_reliable(
        "This is a clean born-digital document with readable native text."
    )
    assert not text_analysis._native_text_is_reliable(
        "���� ���� ���� 123 !!! control replacement noise"
    )


def test_run_tesseract_uses_configured_languages_and_returns_confidence(
    monkeypatch,
):
    captured = {}

    class FakeOutput:
        DICT = "dict"

    class FakeTesseract:
        Output = FakeOutput

        class TesseractNotFoundError(Exception):
            pass

        @staticmethod
        def image_to_data(image, **kwargs):
            captured.update(kwargs)
            return {
                "text": ["Readable", "text"],
                "conf": ["91", "87"],
                "left": [10, 100],
                "top": [10, 10],
                "width": [70, 30],
                "height": [20, 20],
                "block_num": [1, 1],
                "par_num": [1, 1],
                "line_num": [1, 1],
            }

    monkeypatch.setattr(text_analysis, "_pytesseract", lambda: FakeTesseract)
    monkeypatch.setattr(text_analysis.settings, "ocr_languages", "rus+kaz+eng")

    candidate = text_analysis._run_tesseract(
        numpy.full((100, 200), 255, dtype=numpy.uint8),
        "contrast",
    )

    assert captured["lang"] == "rus+kaz+eng"
    assert candidate.text == "Readable text"
    assert candidate.mean_confidence > 87


def test_targeted_retry_recovers_quoted_latin_name_and_protected_term(
    monkeypatch,
):
    words = (
        _word("ТОО", 96, 0, 10),
        _word("«Ка", 78, 60, 10),
        _word("ТАУ»", 74, 115, 10),
        _word("АРІ", 92, 200, 10),
    )
    candidate = OCRCandidate(
        text="ТОО «Ка ТАУ» АРІ",
        words=words,
        mean_confidence=85,
        low_confidence_ratio=0,
        preprocessing="contrast",
    )
    retries = iter(
        (
            OCRCandidate("«KazUAV»", (), 88, 0, "targeted_retry"),
            OCRCandidate("API", (), 96, 0, "targeted_retry"),
        )
    )
    monkeypatch.setattr(
        text_analysis,
        "_run_tesseract",
        lambda *args, **kwargs: next(retries),
    )

    recovered, retry_count, recovery_count = text_analysis._recover_latin_spans(
        candidate,
        numpy.full((100, 300), 255, dtype=numpy.uint8),
    )

    assert recovered.text == "ТОО «KazUAV» API"
    assert retry_count == 2
    assert recovery_count == 2


def test_targeted_retry_preserves_confident_cyrillic_company_name(monkeypatch):
    words = (
        _word("ТОО", 96, 0, 10),
        _word("«САПА»", 96, 60, 10),
    )
    candidate = OCRCandidate(
        text="ТОО «САПА»",
        words=words,
        mean_confidence=96,
        low_confidence_ratio=0,
        preprocessing="contrast",
    )
    monkeypatch.setattr(
        text_analysis,
        "_run_tesseract",
        lambda *args, **kwargs: OCRCandidate(
            "«CAPA»",
            (),
            99,
            0,
            "targeted_retry",
        ),
    )

    recovered, retry_count, recovery_count = text_analysis._recover_latin_spans(
        candidate,
        numpy.full((100, 200), 255, dtype=numpy.uint8),
    )

    assert recovered.text == "ТОО «САПА»"
    assert retry_count == 1
    assert recovery_count == 0


def test_numeric_retry_recovers_low_confidence_score_and_reports_recovery(
    monkeypatch,
):
    words = (
        _word("Рекомендуемая", 96, 0, 10),
        _word("оценка", 93, 80, 10),
        _word("д9г", 36, 150, 10),
    )
    candidate = OCRCandidate(
        text="Рекомендуемая оценка д9г",
        words=words,
        mean_confidence=75,
        low_confidence_ratio=1 / 3,
        preprocessing="contrast",
    )
    monkeypatch.setattr(
        text_analysis,
        "_run_tesseract",
        lambda *args, **kwargs: OCRCandidate(
            "95",
            (),
            63,
            0,
            "targeted_retry",
        ),
    )

    recovered, retry_count, recovery_count = text_analysis._recover_numeric_fields(
        candidate,
        numpy.full((100, 250), 255, dtype=numpy.uint8),
    )

    assert recovered.text == "Рекомендуемая оценка 95"
    assert retry_count == 1
    assert recovery_count == 1
    assert recovered.words[-1].confidence == 63
