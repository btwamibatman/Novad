from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
import re
from typing import Iterable

from app.core.config import settings


PRIVACY_ENGINE_VERSION = "presidio-local-v1"
PRESIDIO_LANGUAGE = "multi"


class PrivacyDetectionError(RuntimeError):
    pass


class PrivacyDetectionUnavailable(PrivacyDetectionError):
    pass


@dataclass(frozen=True)
class PrivacyCategory:
    group: str
    priority: int


# One taxonomy is shared by text masking, PDF redaction and verification.
PRIVACY_TAXONOMY: dict[str, PrivacyCategory] = {
    "IIN": PrivacyCategory("personal", 100),
    "BIN": PrivacyCategory("service", 100),
    "IIN_OR_BIN": PrivacyCategory("personal", 95),
    "QR_CODE": PrivacyCategory("visual", 94),
    "BARCODE": PrivacyCategory("visual", 93),
    "PAYMENT_CARD": PrivacyCategory("financial", 96),
    "EMAIL": PrivacyCategory("personal", 90),
    "PHONE": PrivacyCategory("personal", 90),
    "IBAN": PrivacyCategory("financial", 90),
    "ADDRESS": PrivacyCategory("personal", 85),
    "AMOUNT": PrivacyCategory("financial", 80),
    "DOC_ID": PrivacyCategory("service", 75),
    "ORG": PrivacyCategory("service", 70),
    "PERSON": PrivacyCategory("personal", 60),
    "LOCATION": PrivacyCategory("personal", 55),
    "DATE": PrivacyCategory("context", 50),
    "FACE": PrivacyCategory("visual", 55),
    "SEAL": PrivacyCategory("visual", 55),
    "SIGNATURE": PrivacyCategory("visual", 55),
    "MANUAL": PrivacyCategory("personal", 100),
}

DEFAULT_TEXT_GROUPS = frozenset({"personal", "financial", "service", "context"})
IDENTIFIER_CATEGORIES = frozenset({"IIN", "BIN", "IIN_OR_BIN"})


@dataclass(frozen=True)
class PrivacySpan:
    group: str
    category: str
    text: str
    start: int
    end: int
    confidence: float
    priority: int
    source: str = "presidio"
    recognizer: str = ""
    review_required: bool = False


@dataclass(frozen=True)
class DetectorFailure:
    detector: str
    message: str
    language: str | None = None

    def as_dict(self) -> dict:
        result = {"detector": self.detector, "message": self.message}
        if self.language:
            result["language"] = self.language
        return result


@dataclass(frozen=True)
class TextDetectionResult:
    spans: list[PrivacySpan]
    failures: list[DetectorFailure] = field(default_factory=list)
    detectors: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.failures


class PresidioRuleRecognizer:
    """Factory for the project rules as a real Presidio EntityRecognizer.

    Presidio is imported lazily so API processes which have masking disabled do
    not pay the spaCy import cost. The returned recognizer keeps the existing
    RU/KK/EN high-signal rules while Presidio provides the common orchestration.
    """

    @staticmethod
    def create():
        from presidio_analyzer import EntityRecognizer, RecognizerResult

        from app.services.documents import redaction as rules

        supported = [
            category
            for category, spec in PRIVACY_TAXONOMY.items()
            if spec.group not in {"visual"}
            and category not in IDENTIFIER_CATEGORIES | {"IBAN", "PAYMENT_CARD"}
        ]

        class _Recognizer(EntityRecognizer):
            def __init__(self) -> None:
                super().__init__(
                    supported_entities=supported,
                    supported_language=PRESIDIO_LANGUAGE,
                    name="Project multilingual privacy rules",
                    version=PRIVACY_ENGINE_VERSION,
                )

            def analyze(self, text, entities, nlp_artifacts=None):
                requested = set(entities) & set(self.supported_entities)
                groups = {
                    PRIVACY_TAXONOMY[category].group for category in requested
                }
                results = []
                for candidate in rules.find_text_candidates(text, groups):
                    if candidate.category not in requested:
                        continue
                    results.append(
                        _recognizer_result(
                            RecognizerResult,
                            self,
                            candidate.category,
                            candidate.start,
                            candidate.end,
                            candidate.confidence,
                            candidate.group,
                            candidate.priority,
                            source="presidio-pattern",
                        )
                    )
                return results

        return _Recognizer()


class KazakhstanIdentifierRecognizer:
    """Presidio recognizer for Kazakhstan IIN/BIN with checksum and context."""

    CONTEXT = {
        "IIN": ("иин", "жсн", "iin", "заявитель", "азамат", "өтініш"),
        "BIN": ("бин", "бсн", "bin", "компания", "ұйым", "заңды тұлға"),
        "IIN_OR_BIN": ("иин/бин", "жсн/бсн"),
    }

    @staticmethod
    def create():
        from presidio_analyzer import EntityRecognizer, RecognizerResult

        from app.services.documents import redaction as rules

        class _Recognizer(EntityRecognizer):
            def __init__(self) -> None:
                super().__init__(
                    supported_entities=list(IDENTIFIER_CATEGORIES),
                    supported_language=PRESIDIO_LANGUAGE,
                    name="Kazakhstan IIN BIN recognizer",
                    version=PRIVACY_ENGINE_VERSION,
                    context=sorted(
                        {word for values in KazakhstanIdentifierRecognizer.CONTEXT.values() for word in values}
                    ),
                    country_code="kz",
                )

            def analyze(self, text, entities, nlp_artifacts=None):
                requested = set(entities) & IDENTIFIER_CATEGORIES
                groups = {
                    PRIVACY_TAXONOMY[category].group for category in requested
                }
                if "IIN_OR_BIN" in requested:
                    groups.update({"personal", "service"})
                results = []
                candidates = rules._resolve_text_overlaps(
                    rules._identifier_candidates(text, groups)
                )
                for candidate in candidates:
                    if candidate.category not in requested:
                        continue
                    results.append(
                        _recognizer_result(
                            RecognizerResult,
                            self,
                            candidate.category,
                            candidate.start,
                            candidate.end,
                            candidate.confidence,
                            candidate.group,
                            candidate.priority,
                            source="presidio-kz-id",
                            review_required=candidate.confidence < 0.9,
                        )
                    )
                return results

            def enhance_using_context(
                self,
                text,
                raw_recognizer_results,
                other_raw_recognizer_results,
                nlp_artifacts,
                context=None,
            ):
                lowered = text.casefold()
                external = " ".join(context or ()).casefold()
                for result in raw_recognizer_results:
                    nearby = lowered[max(0, result.start - 60) : min(len(text), result.end + 30)]
                    words = KazakhstanIdentifierRecognizer.CONTEXT.get(
                        result.entity_type, ()
                    )
                    supportive = next(
                        (word for word in words if word in nearby or word in external),
                        None,
                    )
                    if supportive and result.score < 0.99:
                        result.score = min(0.99, result.score + 0.1)
                        result.recognition_metadata[
                            RecognizerResult.IS_SCORE_ENHANCED_BY_CONTEXT_KEY
                        ] = True
                return raw_recognizer_results

        return _Recognizer()


class KazakhstanIBANRecognizer:
    @staticmethod
    def create():
        from presidio_analyzer import EntityRecognizer, RecognizerResult

        class _Recognizer(EntityRecognizer):
            pattern = re.compile(r"\bKZ\d{2}[A-Z0-9]{16}\b", re.IGNORECASE)

            def __init__(self) -> None:
                super().__init__(
                    supported_entities=["IBAN"],
                    supported_language=PRESIDIO_LANGUAGE,
                    name="Kazakhstan IBAN recognizer",
                    version=PRIVACY_ENGINE_VERSION,
                    context=["iban", "иик", "шот", "счет", "счёт", "account"],
                    country_code="kz",
                )

            def analyze(self, text, entities, nlp_artifacts=None):
                if "IBAN" not in entities:
                    return []
                results = []
                for match in self.pattern.finditer(text):
                    valid = validate_kz_iban(match.group(0))
                    results.append(
                        _recognizer_result(
                            RecognizerResult,
                            self,
                            "IBAN",
                            match.start(),
                            match.end(),
                            0.99 if valid else 0.72,
                            "financial",
                            PRIVACY_TAXONOMY["IBAN"].priority,
                            source="presidio-kz-iban",
                            review_required=not valid,
                        )
                    )
                return results

        return _Recognizer()


class PaymentCardRecognizer:
    @staticmethod
    def create():
        from presidio_analyzer import EntityRecognizer, RecognizerResult

        class _Recognizer(EntityRecognizer):
            pattern = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
            context_pattern = re.compile(
                r"(?i)\b(?:card|карта|карты|банк картасы|номер карты|pan)\b"
            )

            def __init__(self) -> None:
                super().__init__(
                    supported_entities=["PAYMENT_CARD"],
                    supported_language=PRESIDIO_LANGUAGE,
                    name="Payment card recognizer",
                    version=PRIVACY_ENGINE_VERSION,
                    context=["card", "карта", "номер карты", "банк картасы", "pan"],
                )

            def analyze(self, text, entities, nlp_artifacts=None):
                if "PAYMENT_CARD" not in entities:
                    return []
                results = []
                for match in self.pattern.finditer(text):
                    value = match.group(0)
                    valid = validate_luhn(value)
                    nearby = text[max(0, match.start() - 45) : match.end() + 20]
                    has_context = bool(self.context_pattern.search(nearby))
                    if not valid and not has_context:
                        continue
                    results.append(
                        _recognizer_result(
                            RecognizerResult,
                            self,
                            "PAYMENT_CARD",
                            match.start(),
                            match.end(),
                            0.98 if valid else 0.7,
                            "financial",
                            PRIVACY_TAXONOMY["PAYMENT_CARD"].priority,
                            source="presidio-payment-card",
                            review_required=not valid,
                        )
                    )
                return results

        return _Recognizer()


class PrivacyEngine:
    def __init__(self, languages: Iterable[str] | None = None) -> None:
        configured = settings.pii_ner_language_list if languages is None else languages
        self.languages = tuple(dict.fromkeys(str(item).strip().lower() for item in configured if str(item).strip()))

    def detect_text(
        self,
        text: str,
        groups: set[str] | frozenset[str] | None = None,
        *,
        include_ner: bool = True,
        fail_closed: bool = False,
    ) -> TextDetectionResult:
        if not text:
            return TextDetectionResult(spans=[], detectors=[])
        selected_groups = set(DEFAULT_TEXT_GROUPS if groups is None else groups)
        entities = [
            category
            for category, spec in PRIVACY_TAXONOMY.items()
            if spec.group in selected_groups and spec.group != "visual"
        ]
        if not entities:
            return TextDetectionResult(spans=[], detectors=[])
        failures: list[DetectorFailure] = []
        detectors: list[str] = []
        spans: list[PrivacySpan] = []

        try:
            analyzer = _presidio_analyzer()
            results = analyzer.analyze(
                text=text,
                language=PRESIDIO_LANGUAGE,
                entities=entities,
                score_threshold=0.01,
            )
            spans.extend(_from_presidio_result(text, result) for result in results)
            detectors.append("presidio")
        except Exception as error:
            failures.append(
                DetectorFailure("presidio", _safe_failure_message(error))
            )

        if include_ner:
            if not self.languages:
                failures.append(
                    DetectorFailure("stanza", "No local NER languages are configured")
                )
            for language in self.languages:
                detector = f"stanza:{language}"
                try:
                    spans.extend(_detect_stanza(text, language, selected_groups))
                    detectors.append(detector)
                except Exception as error:
                    failures.append(
                        DetectorFailure(
                            "stanza",
                            _safe_failure_message(error),
                            language=language,
                        )
                    )

        if failures and fail_closed:
            summary = "; ".join(
                f"{item.detector}{':' + item.language if item.language else ''}: {item.message}"
                for item in failures
            )
            raise PrivacyDetectionUnavailable(
                f"Local privacy detection is incomplete ({summary})"
            )
        return TextDetectionResult(
            spans=_resolve_overlaps(spans, len(text)),
            failures=failures,
            detectors=detectors,
        )


def scan_pdf(
    source: Path,
    groups: set[str],
    progress=None,
) -> tuple[list[dict], dict]:
    """Stable PDF privacy-scan entrypoint used by redaction and verification."""
    from app.services.documents.redaction import detect_redactions

    return detect_redactions(source, groups, progress)


def validate_kz_iban(value: str) -> bool:
    normalized = re.sub(r"\s+", "", value).upper()
    if not re.fullmatch(r"KZ\d{2}[A-Z0-9]{16}", normalized):
        return False
    rearranged = normalized[4:] + normalized[:4]
    numeric = "".join(
        character if character.isdigit() else str(ord(character) - 55)
        for character in rearranged
    )
    remainder = 0
    for character in numeric:
        remainder = (remainder * 10 + int(character)) % 97
    return remainder == 1


def validate_luhn(value: str) -> bool:
    digits = [int(character) for character in value if character.isdigit()]
    if not 13 <= len(digits) <= 19 or len(set(digits)) == 1:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def _recognizer_result(
    result_class,
    recognizer,
    category: str,
    start: int,
    end: int,
    score: float,
    group: str,
    priority: int,
    *,
    source: str,
    review_required: bool = False,
):
    return result_class(
        entity_type=category,
        start=start,
        end=end,
        score=score,
        recognition_metadata={
            result_class.RECOGNIZER_NAME_KEY: recognizer.name,
            result_class.RECOGNIZER_IDENTIFIER_KEY: recognizer.id,
            "group": group,
            "priority": priority,
            "source": source,
            "review_required": review_required,
        },
    )


@lru_cache(maxsize=1)
def _presidio_analyzer():
    try:
        from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
        from presidio_analyzer.nlp_engine import NoOpNlpEngine
    except ImportError as error:
        raise PrivacyDetectionUnavailable(
            "Presidio Analyzer is not installed"
        ) from error

    nlp_engine = NoOpNlpEngine(
        models=[{"lang_code": PRESIDIO_LANGUAGE, "model_name": "local-rules"}]
    )
    nlp_engine.load()
    registry = RecognizerRegistry(supported_languages=[PRESIDIO_LANGUAGE])
    for recognizer in (
        PresidioRuleRecognizer.create(),
        KazakhstanIdentifierRecognizer.create(),
        KazakhstanIBANRecognizer.create(),
        PaymentCardRecognizer.create(),
    ):
        registry.add_recognizer(recognizer)
    return AnalyzerEngine(
        registry=registry,
        nlp_engine=nlp_engine,
        supported_languages=[PRESIDIO_LANGUAGE],
    )


def _from_presidio_result(text: str, result) -> PrivacySpan:
    metadata = result.recognition_metadata or {}
    spec = PRIVACY_TAXONOMY[result.entity_type]
    return PrivacySpan(
        group=str(metadata.get("group", spec.group)),
        category=result.entity_type,
        text=text[result.start : result.end],
        start=int(result.start),
        end=int(result.end),
        confidence=float(result.score),
        priority=int(metadata.get("priority", spec.priority)),
        source=str(metadata.get("source", "presidio")),
        recognizer=str(
            metadata.get("recognizer_name", metadata.get("recognizer_identifier", ""))
        ),
        review_required=bool(metadata.get("review_required", False)),
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
    "CONTACT": "PERSON",
    "MONEY": "AMOUNT",
    "DATE": "DATE",
    "TIME": "DATE",
}


def _detect_stanza(text: str, language: str, groups: set[str]) -> list[PrivacySpan]:
    pipeline = _stanza_pipeline(language, settings.pii_model_dir)
    document = pipeline(text)
    spans: list[PrivacySpan] = []
    for entity in document.ents:
        category = NER_CATEGORY_MAP.get(str(entity.type).upper())
        if not category:
            continue
        spec = PRIVACY_TAXONOMY[category]
        if spec.group not in groups:
            continue
        spans.append(
            PrivacySpan(
                group=spec.group,
                category=category,
                text=text[int(entity.start_char) : int(entity.end_char)],
                start=int(entity.start_char),
                end=int(entity.end_char),
                confidence=0.9,
                priority=spec.priority,
                source="stanza-ner",
                recognizer=f"stanza:{language}",
                review_required=True,
            )
        )
    return spans


@lru_cache(maxsize=8)
def _stanza_pipeline(language: str, model_dir: str):
    try:
        import stanza
    except ImportError as error:
        raise PrivacyDetectionUnavailable("Stanza is not installed") from error
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
        raise PrivacyDetectionUnavailable(
            f"Local Stanza model '{language}' is not installed"
        ) from error


def _resolve_overlaps(spans: list[PrivacySpan], text_length: int) -> list[PrivacySpan]:
    valid = [span for span in spans if 0 <= span.start < span.end <= text_length]
    accepted: list[PrivacySpan] = []
    for span in sorted(
        valid,
        key=lambda item: (
            -item.priority,
            -item.confidence,
            -(item.end - item.start),
            item.start,
            item.category,
        ),
    ):
        if any(span.start < other.end and other.start < span.end for other in accepted):
            continue
        accepted.append(span)
    return sorted(accepted, key=lambda item: (item.start, item.end, item.category))


def _safe_failure_message(error: Exception) -> str:
    if isinstance(error, PrivacyDetectionError):
        return str(error)
    message = str(error).strip()
    return message[:240] if message else error.__class__.__name__
