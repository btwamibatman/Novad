from __future__ import annotations

import re
import tempfile
from pathlib import Path

from langdetect import LangDetectException, detect
from pypdf import PdfReader

from app.models.document import Document
from app.services.file_storage import resolve_stored_path

WORD_PATTERN = re.compile(r"\w+", re.UNICODE)
MIN_PDF_TEXT_SIGNAL_CHARS = 30
OCR_LANGUAGES = ("rus", "kaz", "eng")


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
    return sum(character.isalnum() for character in text) >= MIN_PDF_TEXT_SIGNAL_CHARS


def extract_pdf_text_with_ocr(path: Path) -> str:
    with tempfile.TemporaryDirectory() as temporary_dir:
        ocr_pdf_path = Path(temporary_dir) / "ocr.pdf"
        exit_code = run_ocr(path, ocr_pdf_path)
        if exit_code:
            raise ValueError(f"OCR failed with exit code {exit_code}")
        return extract_pdf_text(ocr_pdf_path)


def run_ocr(input_path: Path, output_path: Path) -> int:
    import ocrmypdf

    return ocrmypdf.ocr(
        input_path,
        output_path,
        language=OCR_LANGUAGES,
        output_type="pdf",
        skip_text=True,
        rotate_pages=True,
        deskew=True,
        jobs=1,
        progress_bar=False,
    )


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
