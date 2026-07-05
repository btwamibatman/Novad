from __future__ import annotations

import re

from langdetect import LangDetectException, detect
from pypdf import PdfReader

from app.models.document import Document
from app.services.file_storage import resolve_stored_path

WORD_PATTERN = re.compile(r"\w+", re.UNICODE)


def extract_text(document: Document) -> str:
    path = resolve_stored_path(document.stored_path)
    if document.content_type == "text/plain":
        return path.read_text(encoding="utf-8", errors="replace")
    if document.content_type == "application/pdf":
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    raise ValueError("Unsupported content type")


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
