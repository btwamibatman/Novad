from __future__ import annotations

from collections import Counter, OrderedDict
from dataclasses import dataclass
from hashlib import sha256
import math
import threading

from app.core.config import settings
from app.services.ai.provider import AIProviderError
from app.services.documents.chunks import ChunkLike, _tokens
from app.services.ollama_provider import OllamaProvider

# Bounded process-local cache of vectors only; documents are always scoped by the caller.
_vectors: OrderedDict[tuple[str, str, str], list[float]] = OrderedDict()
_lock = threading.Lock()


@dataclass
class RetrievalResult:
    chunks: list[ChunkLike]
    method: str
    limitations: list[str]


def _cosine(left, right) -> float:
    if len(left) != len(right):
        raise AIProviderError("Embedding dimensions changed; rebuild the local index")
    divisor = math.sqrt(sum(x * x for x in left) * sum(x * x for x in right))
    return sum(x * y for x, y in zip(left, right)) / divisor if divisor else 0.0


def retrieve(chunks: list[ChunkLike], question: str, *, top_k: int = 5) -> RetrievalResult:
    if not chunks:
        return RetrievalResult([], "bm25", [])
    terms = [Counter(_tokens(chunk.text)) for chunk in chunks]
    query = set(_tokens(question))
    lengths = [sum(row.values()) for row in terms]
    mean_length = max(sum(lengths) / len(chunks), 1)
    frequency = Counter(term for row in terms for term in row)
    lexical = []
    for row, length in zip(terms, lengths):
        score = 0.0
        for term in query:
            count = row[term]
            if count:
                idf = math.log(1 + (len(chunks) - frequency[term] + 0.5) / (frequency[term] + 0.5))
                score += idf * count * 2.5 / (count + 1.5 * (0.25 + 0.75 * length / mean_length))
        lexical.append(score)
    ranked = sorted(range(len(chunks)), key=lambda i: (-lexical[i], chunks[i].chunk_index))
    method, limitations = "bm25", []
    if settings.semantic_search_enabled:
        try:
            provider = OllamaProvider()
            keys = [(settings.ollama_base_url, settings.ollama_embedding_model,
                     sha256(c.text.encode()).hexdigest()) for c in chunks]
            with _lock:
                cached = {key: _vectors[key] for key in keys if key in _vectors}
                for key in cached:
                    _vectors.move_to_end(key)
            missing = list(dict.fromkeys(i for i, key in enumerate(keys) if key not in cached))
            for start in range(0, len(missing), 16):
                indexes = missing[start:start + 16]
                values = provider.embed([chunks[i].text for i in indexes])
                for i, vector in zip(indexes, values):
                    cached[keys[i]] = vector
                with _lock:
                    for i in indexes:
                        _vectors[keys[i]] = cached[keys[i]]
                        _vectors.move_to_end(keys[i])
                    while len(_vectors) > 512:
                        _vectors.popitem(last=False)
            query_vector = provider.embed([
                "Instruct: Given a question, retrieve passages that answer it.\nQuery: " + question
            ])[0]
            semantic = sorted(range(len(chunks)), key=lambda i: (-_cosine(query_vector, cached[keys[i]]), chunks[i].chunk_index))
            # Reciprocal-rank fusion avoids mixing incomparable lexical and cosine scales.
            fused = Counter({i: 1 / (60 + rank) for rank, i in enumerate(semantic, 1)})
            for rank, i in enumerate(ranked, 1):
                if lexical[i] > 0:
                    fused[i] += 1 / (60 + rank)
            ranked = sorted(fused, key=lambda i: (-fused[i], chunks[i].chunk_index))
            method = "hybrid"
        except AIProviderError:
            limitations.append("Смысловой поиск недоступен; использован поиск по словам.")
    return RetrievalResult(
        sorted([chunks[i] for i in ranked[:top_k]], key=lambda c: c.chunk_index),
        method, limitations,
    )
