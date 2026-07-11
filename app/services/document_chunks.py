from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
from typing import Iterable, Protocol

from app.services.text_analysis import ExtractedPage, analyze_text

CHUNK_MAX_CHARS = 1600
CHUNK_OVERLAP_CHARS = 150
RETRIEVAL_TOP_K = 5
RETRIEVAL_MAX_CHARS = 8000

TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)


class ChunkLike(Protocol):
    chunk_index: int
    page_number: int | None
    text: str


@dataclass(frozen=True)
class DocumentChunkAnalysis:
    page_number: int | None
    chunk_index: int
    text: str
    detected_language: str | None
    word_count: int
    char_count: int


def split_text_into_chunks(
    text: str,
    *,
    max_chars: int = CHUNK_MAX_CHARS,
    overlap_chars: int = CHUNK_OVERLAP_CHARS,
) -> list[str]:
    clean_text = text.strip()
    if not clean_text:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(clean_text):
        end = min(start + max_chars, len(clean_text))
        if end < len(clean_text):
            min_boundary = start + max_chars // 2
            boundary = clean_text.rfind("\n", min_boundary, end)
            if boundary == -1:
                boundary = clean_text.rfind(" ", min_boundary, end)
            if boundary != -1:
                end = boundary

        chunk = clean_text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(clean_text):
            break
        start = max(end - overlap_chars, start + 1)

    return chunks


def build_document_chunks(pages: Iterable[ExtractedPage]) -> list[DocumentChunkAnalysis]:
    analyses: list[DocumentChunkAnalysis] = []
    chunk_index = 0

    for page in pages:
        for chunk_text in split_text_into_chunks(page.text):
            detected_language, word_count, char_count = analyze_text(chunk_text)
            analyses.append(
                DocumentChunkAnalysis(
                    page_number=page.page_number,
                    chunk_index=chunk_index,
                    text=chunk_text,
                    detected_language=detected_language,
                    word_count=word_count,
                    char_count=char_count,
                )
            )
            chunk_index += 1

    return analyses


def language_distribution(chunks: Iterable[DocumentChunkAnalysis]) -> dict[str, float]:
    weights: Counter[str] = Counter()
    for chunk in chunks:
        if chunk.detected_language:
            weights[chunk.detected_language] += max(chunk.char_count, 1)

    total = sum(weights.values())
    if not total:
        return {}

    return {
        language: round(count / total, 4)
        for language, count in sorted(weights.items(), key=lambda item: item[1], reverse=True)
    }


def primary_language(distribution: dict[str, float]) -> str | None:
    if not distribution:
        return None
    return max(distribution.items(), key=lambda item: item[1])[0]


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text) if len(token) > 2]


def select_relevant_chunks(
    chunks: Iterable[ChunkLike],
    question: str,
    *,
    top_k: int = RETRIEVAL_TOP_K,
    max_chars: int = RETRIEVAL_MAX_CHARS,
) -> list[ChunkLike]:
    chunk_list = list(chunks)
    if not chunk_list:
        return []

    query_terms = Counter(_tokens(question))
    if not query_terms:
        return chunk_list[:top_k]

    scored_chunks: list[tuple[int, int, ChunkLike]] = []
    for chunk in chunk_list:
        chunk_terms = Counter(_tokens(chunk.text))
        score = sum(chunk_terms[term] * weight for term, weight in query_terms.items())
        scored_chunks.append((score, -chunk.chunk_index, chunk))

    selected = [
        chunk
        for score, _, chunk in sorted(scored_chunks, key=lambda item: item[:2], reverse=True)
        if score > 0
    ]
    if not selected:
        selected = chunk_list

    limited: list[ChunkLike] = []
    total_chars = 0
    for chunk in selected:
        if len(limited) >= top_k:
            break
        if limited and total_chars + len(chunk.text) > max_chars:
            break
        limited.append(chunk)
        total_chars += len(chunk.text)

    return sorted(limited, key=lambda chunk: chunk.chunk_index)


def format_chunks_for_context(chunks: Iterable[ChunkLike]) -> str:
    parts = []
    for chunk in chunks:
        page = f"page {chunk.page_number}" if chunk.page_number is not None else "document"
        parts.append(f"[chunk {chunk.chunk_index}, {page}]\n{chunk.text.strip()}")
    return "\n\n".join(parts)
