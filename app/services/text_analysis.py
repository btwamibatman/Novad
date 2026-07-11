from __future__ import annotations

from dataclasses import dataclass
import re
import tempfile
from pathlib import Path

from docx import Document as DocxDocument
from docx.table import Table
from docx.text.paragraph import Paragraph
from langdetect import LangDetectException, detect
from pypdf import PdfReader, PdfWriter

from app.core.config import settings
from app.models.document import Document
from app.services.file_storage import resolve_stored_path

WORD_PATTERN = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int | None
    text: str
    extraction_method: str


class OCRExtractionError(ValueError):
    pass


def extract_text(document: Document) -> str:
    return "\n".join(page.text for page in extract_text_pages(document))


def extract_text_pages(document: Document) -> list[ExtractedPage]:
    path = resolve_stored_path(document.stored_path)
    if document.content_type == "text/plain":
        return [
            ExtractedPage(
                page_number=None,
                text=path.read_text(encoding="utf-8", errors="replace"),
                extraction_method="txt",
            )
        ]
    if document.content_type == "application/pdf":
        return extract_pdf_pages_with_ocr(path)
    if document.content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return [
            ExtractedPage(
                page_number=None,
                text=extract_docx_text(path),
                extraction_method="docx",
            )
        ]
    raise ValueError("Unsupported content type")


def extract_docx_text(path: Path) -> str:
    try:
        document = DocxDocument(str(path))
        blocks: list[str] = []

        for block in document.iter_inner_content():
            if isinstance(block, Paragraph):
                text = block.text.strip()
            elif isinstance(block, Table):
                rows = [
                    "\t".join(cell.text.strip() for cell in row.cells)
                    for row in block.rows
                ]
                text = "\n".join(row for row in rows if row.strip())
            else:
                continue

            if text:
                blocks.append(text)
    except Exception as error:
        raise ValueError("DOCX extraction failed: file is invalid or corrupted") from error

    return "\n\n".join(blocks)


def extract_pdf_text(path: Path) -> str:
    return join_page_text(extract_pdf_pages(path, extraction_method="pypdf"))


def extract_pdf_pages(path: Path, *, extraction_method: str) -> list[ExtractedPage]:
    reader = PdfReader(str(path))
    return [
        ExtractedPage(
            page_number=index,
            text=page.extract_text() or "",
            extraction_method=extraction_method,
        )
        for index, page in enumerate(reader.pages, start=1)
    ]


def join_page_text(pages: list[ExtractedPage]) -> str:
    return "\n".join(page.text for page in pages)


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
    return join_page_text(extract_pdf_pages_with_ocr(path))


def extract_pdf_pages_with_ocr(path: Path) -> list[ExtractedPage]:
    extracted_pages: list[ExtractedPage] = []
    reader = PdfReader(str(path))

    for index, page in enumerate(reader.pages, start=1):
        extracted_text = page.extract_text() or ""
        if has_enough_text_signal(extracted_text):
            extracted_pages.append(
                ExtractedPage(
                    page_number=index,
                    text=extracted_text,
                    extraction_method="pypdf",
                )
            )
            continue

        extracted_pages.append(
            ExtractedPage(
                page_number=index,
                text=extract_single_pdf_page_with_ocr(page),
                extraction_method="ocr",
            )
        )

    if not has_enough_text_signal(join_page_text(extracted_pages)):
        raise OCRExtractionError(
            "OCR failed: no readable text was found after OCR. Try a clearer scan with better lighting."
        )
    return extracted_pages


def extract_single_pdf_page_with_ocr(page) -> str:
    with tempfile.TemporaryDirectory() as temporary_dir:
        input_pdf_path = Path(temporary_dir) / "input.pdf"
        ocr_pdf_path = Path(temporary_dir) / "ocr.pdf"
        writer = PdfWriter()
        writer.add_page(page)
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
        return join_page_text(extracted_pages)


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
