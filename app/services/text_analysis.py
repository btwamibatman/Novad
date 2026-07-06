from __future__ import annotations

import re
import tempfile
from pathlib import Path

from langdetect import LangDetectException, detect
from pypdf import PdfReader

from app.core.config import settings
from app.models.document import Document
from app.services.file_storage import resolve_stored_path

WORD_PATTERN = re.compile(r"\w+", re.UNICODE)


class OCRExtractionError(ValueError):
    pass


def extract_text(document: Document) -> str:
    path = resolve_stored_path(document.stored_path)
    if document.content_type == "text/plain":
        return path.read_text(encoding="utf-8", errors="replace")
    if document.content_type == "application/pdf":
        extracted_text = extract_pdf_text(path)
        if has_enough_text_signal(extracted_text):
            return extracted_text
        return extract_pdf_text_with_ocr(path)
    raise ValueError("Unsupported content type")


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def has_enough_text_signal(text: str) -> bool:
    return sum(character.isalnum() for character in text) >= settings.ocr_min_text_signal_chars


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
    with tempfile.TemporaryDirectory() as temporary_dir:
        ocr_pdf_path = Path(temporary_dir) / "ocr.pdf"
        try:
            exit_code = run_ocr(path, ocr_pdf_path)
        except ImportError as error:
            raise OCRExtractionError("OCR failed: OCRmyPDF is not installed in this environment") from error
        except Exception as error:
            raise OCRExtractionError(format_ocr_error(error)) from error
        if exit_code:
            raise OCRExtractionError(f"OCR failed: OCR engine exited with code {exit_code}")

        extracted_text = extract_pdf_text(ocr_pdf_path)
        if not has_enough_text_signal(extracted_text):
            raise OCRExtractionError(
                "OCR failed: no readable text was found after OCR. Try a clearer scan with better lighting."
            )
        return extracted_text


def run_ocr(input_path: Path, output_path: Path) -> int:
    import ocrmypdf

    return ocrmypdf.ocr(
        input_path,
        output_path,
        language=configured_ocr_languages(),
        output_type="pdf",
        skip_text=True,
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
