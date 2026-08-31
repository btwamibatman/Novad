from app.services.text_analysis import ExtractedPage, assess_extraction_quality


def test_native_text_quality_is_high_without_manual_review():
    assessment = assess_extraction_quality(
        [
            ExtractedPage(
                page_number=1,
                text="This native PDF page contains enough clean text for analysis.",
                extraction_method="pypdf",
            )
        ]
    )

    assert assessment.quality == "high"
    assert assessment.requires_manual_review is False
    assert assessment.meta["manual_review_pages"] == []


def test_clean_ocr_text_is_advisory_and_requires_manual_review():
    assessment = assess_extraction_quality(
        [
            ExtractedPage(
                page_number=2,
                text=(
                    "Документ содержит достаточно читаемый распознанный текст, "
                    "но имена и даты необходимо сверить с изображением страницы."
                ),
                extraction_method="ocr",
            )
        ]
    )

    assert assessment.quality == "medium"
    assert assessment.requires_manual_review is True
    assert assessment.meta["manual_review_pages"] == [2]


def test_mixed_script_ocr_text_is_low_quality():
    assessment = assess_extraction_quality(
        [
            ExtractedPage(
                page_number=1,
                text=(
                    "Доcумент напиcан cо смешанными cимволами. "
                    "Такие cлова нельзя считать точным результатом распознавания."
                ),
                extraction_method="ocr",
            )
        ]
    )

    assert assessment.quality == "low"
    assert assessment.meta["low_quality_pages"] == [1]
    assert assessment.meta["pages"][0]["mixed_script_token_count"] >= 2
