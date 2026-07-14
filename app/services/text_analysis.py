from __future__ import annotations

from dataclasses import dataclass
import re
import tempfile
import unicodedata
from pathlib import Path

from langdetect import LangDetectException, detect
from pypdf import PdfReader, PdfWriter

from app.core.config import settings
from app.models.document import Document
from app.services.file_storage import resolve_stored_path

WORD_PATTERN = re.compile(r"\w+", re.UNICODE)
LETTER_TOKEN_PATTERN = re.compile(r"[^\W\d_]+", re.UNICODE)


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int | None
    text: str
    extraction_method: str


@dataclass(frozen=True)
class ExtractionQualityAssessment:
    quality: str
    requires_manual_review: bool
    meta: dict


class OCRExtractionError(ValueError):
    pass


def extract_text(document: Document) -> str:
    return "\n".join(page.text for page in extract_text_pages(document))


def extract_text_pages(document: Document) -> list[ExtractedPage]:
    path = resolve_stored_path(document.stored_path)
    if document.content_type == "application/pdf":
        return extract_pdf_pages_with_ocr(path)
    raise ValueError("Only PDF documents can be analyzed")


def extract_pdf_text(path: Path) -> str:
    return join_page_text(extract_pdf_pages(path, extraction_method="pypdf"))


def extract_pdf_pages(path: Path, *, extraction_method: str) -> list[ExtractedPage]:
    reader = PdfReader(str(path))
    return [
        ExtractedPage(
            page_number=index,
            text=extract_page_text(page),
            extraction_method=extraction_method,
        )
        for index, page in enumerate(reader.pages, start=1)
    ]


def extract_page_text(page) -> str:
    try:
        return page.extract_text() or ""
    except Exception:
        return ""


def join_page_text(pages: list[ExtractedPage]) -> str:
    return "\n".join(page.text for page in pages)


def assess_extraction_quality(
    pages: list[ExtractedPage],
) -> ExtractionQualityAssessment:
    page_assessments = [_assess_page_quality(page) for page in pages]
    ocr_pages = [
        page["page_number"]
        for page in page_assessments
        if page["extraction_method"] == "ocr"
    ]
    low_quality_pages = [
        page["page_number"]
        for page in page_assessments
        if page["quality"] == "low"
    ]

    if low_quality_pages:
        quality = "low"
    elif ocr_pages:
        quality = "medium"
    else:
        quality = "high"

    reasons = []
    if ocr_pages:
        reasons.append(
            "OCR was used; verify names, dates, identifiers and signature-related fields "
            "against the PDF image."
        )
    if low_quality_pages:
        reasons.append(
            "Weak OCR structure was detected on one or more pages; extracted wording "
            "must not be treated as exact."
        )

    requires_manual_review = bool(ocr_pages or low_quality_pages)
    return ExtractionQualityAssessment(
        quality=quality,
        requires_manual_review=requires_manual_review,
        meta={
            "heuristic": True,
            "requires_manual_review": requires_manual_review,
            "page_count": len(page_assessments),
            "ocr_page_count": len(ocr_pages),
            "manual_review_pages": ocr_pages,
            "low_quality_pages": low_quality_pages,
            "reasons": reasons,
            "pages": page_assessments,
        },
    )


def _assess_page_quality(page: ExtractedPage) -> dict:
    text = page.text.strip()
    non_whitespace = [character for character in text if not character.isspace()]
    alphanumeric_count = sum(character.isalnum() for character in non_whitespace)
    suspicious_character_count = sum(
        _is_suspicious_character(character) for character in non_whitespace
    )
    letter_tokens = LETTER_TOKEN_PATTERN.findall(text)
    mixed_script_token_count = sum(
        len(_token_scripts(token)) > 1 for token in letter_tokens
    )
    alphanumeric_ratio = (
        alphanumeric_count / len(non_whitespace) if non_whitespace else 0.0
    )
    mixed_script_ratio = (
        mixed_script_token_count / len(letter_tokens) if letter_tokens else 0.0
    )
    suspicious_character_ratio = (
        suspicious_character_count / len(non_whitespace) if non_whitespace else 0.0
    )

    reasons = []
    quality = "medium" if page.extraction_method == "ocr" else "high"
    if not has_enough_text_signal(text):
        quality = "low"
        reasons.append("No reliable text signal was found on this page.")
    if alphanumeric_ratio < 0.55 and len(non_whitespace) >= 30:
        quality = "low"
        reasons.append("The page contains too much non-alphanumeric OCR noise.")
    if suspicious_character_count >= 2 and suspicious_character_ratio >= 0.02:
        quality = "low"
        reasons.append("The page contains suspicious replacement or control characters.")
    if mixed_script_token_count >= 2 and mixed_script_ratio >= 0.03:
        quality = "low"
        reasons.append("The page contains many words with mixed writing systems.")

    return {
        "page_number": page.page_number,
        "extraction_method": page.extraction_method,
        "quality": quality,
        "character_count": len(text),
        "alphanumeric_ratio": round(alphanumeric_ratio, 3),
        "mixed_script_token_count": mixed_script_token_count,
        "suspicious_character_count": suspicious_character_count,
        "reasons": reasons,
    }


def _token_scripts(token: str) -> set[str]:
    scripts = set()
    for character in token:
        name = unicodedata.name(character, "")
        if "CYRILLIC" in name:
            scripts.add("cyrillic")
        elif "LATIN" in name:
            scripts.add("latin")
    return scripts


def _is_suspicious_character(character: str) -> bool:
    return character in {"\x00", "\ufffd"} or unicodedata.category(character) in {
        "Cc",
        "Cs",
    }


def has_enough_text_signal(text: str) -> bool:
    alphanumeric_count = sum(character.isalnum() for character in text)
    if alphanumeric_count < settings.ocr_min_text_signal_chars:
        return False

    non_whitespace = [character for character in text if not character.isspace()]
    if not non_whitespace:
        return False
    suspicious_count = sum(character in {"\x00", "\ufffd"} for character in non_whitespace)
    return suspicious_count / len(non_whitespace) < 0.1


def configured_ocr_languages() -> tuple[str, ...]:
    languages = tuple(
        language.strip()
        for language in settings.ocr_languages.replace(",", "+").split("+")
        if language.strip()
    )
    if not languages:
        raise OCRExtractionError("OCR failed: no OCR languages are configured")
    return languages


def extract_pdf_text_with_ocr(path: Path) -> str:
    return join_page_text(extract_pdf_pages_with_ocr(path))


def extract_pdf_pages_with_ocr(path: Path) -> list[ExtractedPage]:
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        raise OCRExtractionError("PDF analysis failed: password-protected PDFs are not supported")

    native_texts = [extract_page_text(page) for page in reader.pages]
    weak_page_indexes = [
        index
        for index, text in enumerate(native_texts)
        if not has_enough_text_signal(text)
    ]
    ocr_texts = extract_pdf_pages_with_batch_ocr(reader, weak_page_indexes)

    extracted_pages = [
        ExtractedPage(
            page_number=index + 1,
            text=ocr_texts.get(index, native_texts[index]),
            extraction_method="ocr" if index in ocr_texts else "pypdf",
        )
        for index in range(len(reader.pages))
    ]

    if not has_enough_text_signal(join_page_text(extracted_pages)):
        raise OCRExtractionError(
            "OCR failed: no readable text was found after OCR. Try a clearer scan with better lighting."
        )
    return extracted_pages


def extract_pdf_pages_with_batch_ocr(
    reader: PdfReader,
    page_indexes: list[int],
) -> dict[int, str]:
    if not page_indexes:
        return {}

    with tempfile.TemporaryDirectory() as temporary_dir:
        input_pdf_path = Path(temporary_dir) / "input.pdf"
        ocr_pdf_path = Path(temporary_dir) / "ocr.pdf"
        writer = PdfWriter()
        for page_index in page_indexes:
            writer.add_page(reader.pages[page_index])
        with input_pdf_path.open("wb") as file:
            writer.write(file)

        try:
            exit_code = run_ocr(input_pdf_path, ocr_pdf_path)
        except ImportError as error:
            raise OCRExtractionError("OCR failed: OCRmyPDF is not installed in this environment") from error
        except Exception as error:
            raise OCRExtractionError(format_ocr_error(error)) from error
        if exit_code:
            raise OCRExtractionError(f"OCR failed: OCR engine exited with code {exit_code}")

        extracted_pages = extract_pdf_pages(ocr_pdf_path, extraction_method="ocr")
        if len(extracted_pages) != len(page_indexes):
            raise OCRExtractionError("OCR failed: page count changed during processing")
        return {
            original_index: extracted_page.text
            for original_index, extracted_page in zip(page_indexes, extracted_pages, strict=True)
        }


def run_ocr(input_path: Path, output_path: Path) -> int:
    import ocrmypdf

    return ocrmypdf.ocr(
        input_path,
        output_path,
        language=configured_ocr_languages(),
        output_type="pdf",
        force_ocr=True,
        rotate_pages=True,
        deskew=True,
        jobs=1,
        progress_bar=False,
    )


def format_ocr_error(error: Exception) -> str:
    message = str(error).strip()
    lower_message = message.lower()

    if (
        "traineddata" in lower_message
        or "failed loading language" in lower_message
        or "error opening data file" in lower_message
    ):
        return f"OCR failed: configured language data is missing ({settings.ocr_languages})"
    if "tesseract" in lower_message and ("not found" in lower_message or "not installed" in lower_message):
        return "OCR failed: Tesseract is not installed in this environment"
    if message:
        return f"OCR failed: {message}"
    return "OCR failed: OCR engine could not process this document"


def analyze_text(text: str) -> tuple[str | None, int, int]:
    clean_text = text.strip()
    if not clean_text:
        raise ValueError("No extractable text was found")

    word_count = len(WORD_PATTERN.findall(clean_text))
    char_count = len(clean_text)

    try:
        detected_language = detect(clean_text)
    except LangDetectException:
        detected_language = None

    return detected_language, word_count, char_count
