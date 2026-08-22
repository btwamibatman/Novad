from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
from typing import Protocol

from app.core.config import settings
from app.services.privacy_detection import (
    DEFAULT_TEXT_GROUPS,
    NER_CATEGORY_MAP,
    PRIVACY_ENGINE_VERSION,
    PRIVACY_TAXONOMY,
    PrivacyDetectionError,
    PrivacyEngine,
    _stanza_pipeline,
)


PLACEHOLDER_PATTERN = re.compile(r"\[([A-Z][A-Z_]+)_(\d+)\]")
POTENTIAL_PLACEHOLDER_PATTERN = re.compile(r"\[[A-Za-z][A-Za-z_-]*[_-]\d+\]")


class PIIMaskingError(RuntimeError):
    pass


class PIIMaskingUnavailable(PIIMaskingError):
    pass


@dataclass(frozen=True)
class PIISpan:
    start: int
    end: int
    category: str
    score: float = 1.0


@dataclass(frozen=True)
class PIIMaskingMeta:
    applied: bool
    entity_count: int
    categories: dict[str, int]
    engine_version: str | None = None
    detectors: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        result = {
            "applied": self.applied,
            "entity_count": self.entity_count,
            "categories": self.categories,
        }
        if self.engine_version:
            result["engine_version"] = self.engine_version
        if self.detectors:
            result["detectors"] = list(self.detectors)
        return result


class PIIRecognizer(Protocol):
    def find(self, text: str) -> list[PIISpan]: ...


class RegexPIIRecognizer:
    """Backward-compatible adapter over the shared local Presidio rules."""

    def __init__(self) -> None:
        self._engine = PrivacyEngine(languages=[])

    def find(self, text: str) -> list[PIISpan]:
        try:
            result = self._engine.detect_text(
                text,
                set(DEFAULT_TEXT_GROUPS),
                include_ner=False,
                fail_closed=True,
            )
        except PrivacyDetectionError as error:
            raise PIIMaskingUnavailable(str(error)) from error
        return [
            PIISpan(span.start, span.end, span.category, span.confidence)
            for span in result.spans
        ]


class StanzaPIIRecognizer:
    """Backward-compatible adapter using the shared privacy taxonomy."""

    def __init__(self, languages: list[str]) -> None:
        if not languages:
            raise PIIMaskingUnavailable("PII masking has no configured NER languages")
        self.languages = languages

    def find(self, text: str) -> list[PIISpan]:
        spans: list[PIISpan] = []
        for language in self.languages:
            try:
                pipeline = _stanza_pipeline(language, settings.pii_model_dir)
                document = pipeline(text)
            except Exception as error:
                raise PIIMaskingUnavailable(
                    f"Local PII NER failed for language '{language}'"
                ) from error
            for entity in document.ents:
                category = NER_CATEGORY_MAP.get(str(entity.type).upper())
                if category and PRIVACY_TAXONOMY[category].group in DEFAULT_TEXT_GROUPS:
                    spans.append(
                        PIISpan(
                            start=int(entity.start_char),
                            end=int(entity.end_char),
                            category=category,
                            score=0.9,
                        )
                    )
        return spans


class PIIMaskingSession:
    def __init__(
        self,
        recognizers: list[PIIRecognizer] | None = None,
        *,
        enabled: bool | None = None,
    ) -> None:
        self.enabled = settings.pii_masking_enabled if enabled is None else enabled
        self.recognizers = recognizers or []
        self._privacy_engine = PrivacyEngine() if recognizers is None and self.enabled else None
        self._token_to_value: dict[str, str] = {}
        self._value_to_token: dict[tuple[str, str], str] = {}
        self._category_counts: Counter[str] = Counter()
        self._detectors: tuple[str, ...] = ()

    @property
    def meta(self) -> PIIMaskingMeta:
        return PIIMaskingMeta(
            applied=self.enabled,
            entity_count=len(self._token_to_value),
            categories=dict(sorted(self._category_counts.items())),
            engine_version=(
                PRIVACY_ENGINE_VERSION if self._privacy_engine is not None else None
            ),
            detectors=self._detectors,
        )

    def mask(self, text: str) -> str:
        if not self.enabled or not text:
            return text
        try:
            if self._privacy_engine is not None:
                result = self._privacy_engine.detect_text(
                    text,
                    set(DEFAULT_TEXT_GROUPS),
                    include_ner=True,
                    fail_closed=True,
                )
                spans = [
                    PIISpan(span.start, span.end, span.category, span.confidence)
                    for span in result.spans
                ]
                self._detectors = tuple(dict.fromkeys((*self._detectors, *result.detectors)))
            else:
                spans = []
                for recognizer in self.recognizers:
                    spans.extend(recognizer.find(text))
        except PIIMaskingError:
            raise
        except PrivacyDetectionError as error:
            raise PIIMaskingUnavailable(str(error)) from error
        except Exception as error:
            raise PIIMaskingUnavailable("Local PII masking failed") from error
        accepted = _non_overlapping_spans(spans, len(text))
        if not accepted:
            return text

        parts: list[str] = []
        cursor = 0
        for span in accepted:
            parts.append(text[cursor : span.start])
            value = text[span.start : span.end]
            parts.append(self._token_for(span.category, value))
            cursor = span.end
        parts.append(text[cursor:])
        return "".join(parts)

    def restore(self, text: str) -> str:
        if not self.enabled:
            return text
        for match in POTENTIAL_PLACEHOLDER_PATTERN.finditer(text):
            token = match.group(0)
            if not PLACEHOLDER_PATTERN.fullmatch(token) or token not in self._token_to_value:
                raise PIIMaskingError(
                    "AI response contained an unknown privacy placeholder"
                )
        restored = text
        for token, value in sorted(
            self._token_to_value.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            restored = restored.replace(token, value)
        return restored

    def _token_for(self, category: str, value: str) -> str:
        normalized = re.sub(r"\s+", " ", value).strip().casefold()
        key = category, normalized
        existing = self._value_to_token.get(key)
        if existing:
            return existing
        index = self._category_counts[category] + 1
        token = f"[{category}_{index}]"
        self._category_counts[category] = index
        self._value_to_token[key] = token
        self._token_to_value[token] = value
        return token


def _non_overlapping_spans(spans: list[PIISpan], text_length: int) -> list[PIISpan]:
    valid = [span for span in spans if 0 <= span.start < span.end <= text_length]
    valid.sort(
        key=lambda span: (
            span.start,
            -(span.end - span.start),
            -span.score,
            span.category,
        )
    )
    accepted: list[PIISpan] = []
    cursor = 0
    for span in valid:
        if span.start < cursor:
            continue
        accepted.append(span)
        cursor = span.end
    return accepted
