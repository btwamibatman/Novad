from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
import re
from typing import Protocol

from app.core.config import settings

PLACEHOLDER_PATTERN = re.compile(r"\[([A-Z][A-Z_]+)_(\d+)\]")
POTENTIAL_PLACEHOLDER_PATTERN = re.compile(
    r"\[[A-Za-z][A-Za-z_-]*[_-]\d+\]"
)


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

    def as_dict(self) -> dict:
        return {
            "applied": self.applied,
            "entity_count": self.entity_count,
            "categories": self.categories,
        }


class PIIRecognizer(Protocol):
    def find(self, text: str) -> list[PIISpan]: ...


REGEX_RECOGNIZERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "EMAIL",
        re.compile(r"(?<![\w.-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w.-])", re.I),
    ),
    ("IBAN", re.compile(r"\bKZ\d{2}[A-Z0-9]{16}\b", re.I)),
    (
        "IIN_BIN",
        re.compile(
            r"(?i)(?:(?:ИИН|БИН|ЖСН|БСН|IIN|BIN)\s*[:№#-]?\s*)\d{12}\b"
        ),
    ),
    (
        "PHONE",
        re.compile(
            r"(?<!\d)(?:\+?7|8)[\s()\-]*\d{3}[\s()\-]*"
            r"\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)"
        ),
    ),
    (
        "DOC_ID",
        re.compile(
            r"(?i)\b(?:договор|контракт|приказ|акт|сч[её]т|document|contract)"
            r"\s*(?:№|no\.?|#)?\s*[A-ZА-ЯӘҒҚҢӨҰҮҺ0-9][\w./-]{2,}\b"
        ),
    ),
    (
        "AMOUNT",
        re.compile(
            r"(?<!\w)\d[\d\s]*(?:[.,]\d+)?\s*"
            r"(?:₸|₽|\$|€|тенге|руб(?:лей|ля)?|KZT|RUB|USD|EUR|"
            r"млн|тыс\.?)\b",
            re.I,
        ),
    ),
    (
        "DATE",
        re.compile(
            r"(?<!\d)(?:0?[1-9]|[12]\d|3[01])[./-]"
            r"(?:0?[1-9]|1[0-2])[./-](?:19|20)\d{2}(?!\d)"
        ),
    ),
    (
        "ADDRESS",
        re.compile(
            r"(?i)\b(?:ул(?:ица)?|проспект|пр-т|мкр|микрорайон|"
            r"street|avenue|address|мекенжай)\s+[^\n,;]{3,80}"
        ),
    ),
)

NER_CATEGORY_MAP = {
    "PERSON": "PERSON",
    "PER": "PERSON",
    "ORGANIZATION": "ORG",
    "ORGANISATION": "ORG",
    "ORG": "ORG",
    "GPE": "LOCATION",
    "LOC": "LOCATION",
    "LOCATION": "LOCATION",
    "FACILITY": "LOCATION",
    "CONTACT": "CONTACT",
    "MONEY": "AMOUNT",
    "DATE": "DATE",
    "TIME": "DATE",
}


class RegexPIIRecognizer:
    def find(self, text: str) -> list[PIISpan]:
        spans: list[PIISpan] = []
        for category, pattern in REGEX_RECOGNIZERS:
            spans.extend(
                PIISpan(match.start(), match.end(), category)
                for match in pattern.finditer(text)
            )
        return spans


class StanzaPIIRecognizer:
    def __init__(self, languages: list[str]) -> None:
        if not languages:
            raise PIIMaskingUnavailable("PII masking has no configured NER languages")
        self.languages = languages

    def find(self, text: str) -> list[PIISpan]:
        spans: list[PIISpan] = []
        for language in self.languages:
            pipeline = _stanza_pipeline(language, settings.pii_model_dir)
            try:
                document = pipeline(text)
            except Exception as error:
                raise PIIMaskingUnavailable(
                    f"Local PII NER failed for language '{language}'"
                ) from error
            for entity in document.ents:
                category = NER_CATEGORY_MAP.get(str(entity.type).upper())
                if category:
                    spans.append(
                        PIISpan(
                            start=int(entity.start_char),
                            end=int(entity.end_char),
                            category=category,
                            score=0.9,
                        )
                    )
        return spans


@lru_cache(maxsize=8)
def _stanza_pipeline(language: str, model_dir: str):
    try:
        import stanza
    except ImportError as error:
        raise PIIMaskingUnavailable(
            "Local PII masking is unavailable: Stanza is not installed"
        ) from error
    try:
        return stanza.Pipeline(
            lang=language,
            processors="tokenize,ner",
            model_dir=model_dir,
            download_method=None,
            use_gpu=False,
            verbose=False,
        )
    except Exception as error:
        raise PIIMaskingUnavailable(
            f"Local PII model '{language}' is not installed"
        ) from error


class PIIMaskingSession:
    def __init__(
        self,
        recognizers: list[PIIRecognizer] | None = None,
        *,
        enabled: bool | None = None,
    ) -> None:
        self.enabled = settings.pii_masking_enabled if enabled is None else enabled
        if recognizers is None and self.enabled:
            recognizers = [
                RegexPIIRecognizer(),
                StanzaPIIRecognizer(settings.pii_ner_language_list),
            ]
        self.recognizers = recognizers or []
        self._token_to_value: dict[str, str] = {}
        self._value_to_token: dict[tuple[str, str], str] = {}
        self._category_counts: Counter[str] = Counter()

    @property
    def meta(self) -> PIIMaskingMeta:
        return PIIMaskingMeta(
            applied=self.enabled,
            entity_count=len(self._token_to_value),
            categories=dict(sorted(self._category_counts.items())),
        )

    def mask(self, text: str) -> str:
        if not self.enabled or not text:
            return text
        spans: list[PIISpan] = []
        try:
            for recognizer in self.recognizers:
                spans.extend(recognizer.find(text))
        except PIIMaskingError:
            raise
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
    valid = [
        span
        for span in spans
        if 0 <= span.start < span.end <= text_length
    ]
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
