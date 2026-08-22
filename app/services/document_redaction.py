from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
from pathlib import Path
import re
import string

import numpy as np
import pymupdf

from app.core.config import settings


class RedactionError(RuntimeError):
    pass


PROTECTED_PDF_RENDER_DPI = 200
PROTECTED_PDF_JPEG_QUALITY = 90
PROTECTED_PDF_RENDER_PROFILES = (
    (PROTECTED_PDF_RENDER_DPI, PROTECTED_PDF_JPEG_QUALITY),
    (180, 85),
    (150, 80),
    (120, 70),
    (96, 60),
)


@dataclass(frozen=True)
class TextPattern:
    group: str
    category: str
    pattern: re.Pattern[str]
    confidence: float
    priority: int
    value_group: str | int = 0


@dataclass(frozen=True)
class TextCandidate:
    group: str
    category: str
    text: str
    start: int
    end: int
    confidence: float
    priority: int


@dataclass(frozen=True)
class PageTextLayer:
    source: str
    words: list[dict]
    text: str
    confidence: float | None = None


CYRILLIC_UPPER = "А-ЯӘҒҚҢӨҰҮҺЁІ"
CYRILLIC_LOWER = "а-яәғқңөұүһёі"
NAME_TOKEN = rf"(?:[{CYRILLIC_UPPER}A-Z][{CYRILLIC_LOWER}a-z'’\-]{{1,40}}|[{CYRILLIC_UPPER}A-Z]{{2,40}})"
INITIALS = rf"[{CYRILLIC_UPPER}A-Z]\.\s*[{CYRILLIC_UPPER}A-Z]\.?"
PERSON_VALUE = rf"(?:{NAME_TOKEN}\s+{INITIALS}|{NAME_TOKEN}(?:\s+{NAME_TOKEN}){{1,2}})"

PERSON_LABEL_CONTEXT_PATTERN = re.compile(
    rf"(?<!\w)(?i:Ф\.?\s*И\.?\s*О\.?|граждан(?:ин|ка)|азамат(?:ша)?|"
    rf"заявитель|өтініш\s+беруші)(?!\w)"
    rf"(?:\s*[:—–-]\s*|\s+)(?P<value>{PERSON_VALUE})"
)
PERSON_FULL_LABEL_PATTERN = re.compile(
    rf"(?<!\w)(?i:фамилия\s*,?\s*имя\s*,?\s*отчество|"
    rf"тегі\s*,?\s*аты\s*,?\s*әкесінің\s+аты)(?!\w)"
    rf"[ \t]*(?:\([^\n)]{{1,80}}\)[ \t]*)?[:—–-][ \t]*(?P<value>{PERSON_VALUE})"
)
PERSON_ROLE_CONTEXT_PATTERN = re.compile(
    rf"(?<!\w)(?i:директор|руководитель|басшы|председатель|төраға|подписал(?:а)?|"
    rf"қол\s+қойған|представитель|өкіл|судья|нотариус)"
    rf"[ \t]*(?:[:—–-][ \t]*)?(?P<value>{NAME_TOKEN}[ \t]+{INITIALS})"
)

ADDRESS_LABEL_PATTERN = re.compile(
    r"(?im)(?<!электронный\s)(?<!электронная\s)(?<!электрондық\s)\b"
    r"(?:юридический\s+адрес|фактический\s+адрес|"
    r"адрес(?:\s+(?:места\s+(?:жительства|регистрации)|местонахождения|проживания))?|"
    r"место\s+проживания|мекенжай(?:ы)?|тұрғылықты\s+жер(?:інің)?(?:\s+мекенжайы)?|"
    r"тіркелген\s+жерінің\s+мекенжайы)\b[ \t]*[:—–-][ \t]*"
    r"(?P<value>[^\n;]{3,180}?)(?=\s+(?:тел(?:ефон)?|phone|e-?mail|"
    r"электрон(?:дық|ная)\s+(?:пошта|почта)|ИИН|ЖСН|БИН|БСН)\s*[:.-]|[;\n]|$)"
)

ADDRESS_LINE_PATTERN = re.compile(
    rf"(?im)(?P<value>\b(?:(?:Республика\s+Казахстан|Қазақстан\s+Республикасы)\s*,\s*)?"
    rf"(?:(?:г(?:ород)?\.?\s*)?[{CYRILLIC_UPPER}][\w'’\-]+|"
    rf"[{CYRILLIC_UPPER}][\w'’\-]+\s+(?:облысы|ауданы|қаласы))"
    rf"(?:\s+(?:область|облысы|район|ауданы|город|қаласы|қ\.))?\s*,\s*[^\n;]{{0,120}}?"
    rf"(?:ул(?:ица)?\.?|көшесі|к-сі|проспект|пр-т|даңғылы|мкр\.?|микрорайон|"
    rf"шағын\s+аудан|ықшам\s+аудан)[^\n;]{{1,100}}?"
    rf"(?:\b(?:д(?:ом)?|үй|кв(?:артира)?|пәтер|офис|кеңсе|строение)\b\s*[:№.\-]?\s*|,\s*)"
    rf"\d+[A-Za-zА-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІі]?(?:[^\n;]{{0,60}}))"
)

LEGAL_FORM = r"(?:ТОО|ЖШС|АО|АҚ|ИП|ЖК|ГУ|ММ|КГУ|КММ|РГУ|РММ|ГККП|МКҚК|РГП|РМК|КГП|КМК|ОО|ҚБ|ОФ|ҚҚ|ПК|ӨК)"
ORG_FORM_PREFIX_PATTERN = re.compile(
    rf"(?P<value>\b{LEGAL_FORM}(?:\s+на\s+ПХВ|\s+ШЖҚ)?\s+"
    rf"(?:[«\"][^»\"\n]{{2,120}}[»\"]|[{CYRILLIC_UPPER}A-Z][^\n,;]{{2,100}}))"
)
ORG_FORM_SUFFIX_PATTERN = re.compile(
    rf"(?P<value>[«\"][^»\"\n]{{2,120}}[»\"]\s*{LEGAL_FORM}\b)"
)
ORG_FULL_FORM_PATTERN = re.compile(
    r"(?i)(?P<value>\b(?:товарищество\s+с\s+ограниченной\s+ответственностью|"
    r"акционерное\s+общество|жауапкершілігі\s+шектеулі\s+серіктестігі|"
    r"акционерлік\s+қоғам)\s+[«\"][^»\"\n]{2,120}[»\"])"
)
ORG_RU_BODY_PATTERN = re.compile(
    rf"(?i)(?P<value>\b(?:министерство|комитет|департамент|управление)\s+"
    rf"[^\n,;]{{2,100}}?(?:Республики\s+Казахстан|(?:города|области|района)\s+"
    rf"[{CYRILLIC_UPPER}][\w'’\-]+))"
)
ORG_RU_LOCATION_PATTERN = re.compile(
    rf"(?i)(?P<value>\b(?:акимат|прокуратура|маслихат|суд)\s+"
    rf"(?:города|области|района)\s+[{CYRILLIC_UPPER}][\w'’\-]+(?:[ \t]+[{CYRILLIC_UPPER}][\w'’\-]+)?)"
)
ORG_KK_BODY_PATTERN = re.compile(
    rf"(?P<value>\b(?:Қазақстан\s+Республикасының\s+)?[{CYRILLIC_UPPER}][\w'’\-]+"
    rf"(?:\s+[{CYRILLIC_UPPER}{CYRILLIC_LOWER}][\w'’\-]+){{0,7}}\s+"
    rf"(?:министрлігі|комитеті|департаменті|басқармасы))\b"
)
ORG_KK_LOCATION_PATTERN = re.compile(
    rf"(?P<value>\b[{CYRILLIC_UPPER}][\w'’\-]+(?:\s+[{CYRILLIC_UPPER}][\w'’\-]+)?\s+"
    rf"(?:облысының|қаласының|ауданының)\s+(?:әкімдігі|мәслихаты|соты|прокуратурасы))\b"
)

DOC_ID_MARKED_PATTERN = re.compile(
    r"(?i)\b(?:договор|контракт|приказ|акт|сч[её]т)\b[ \t]*(?:№|no\.?|#)[ \t]*"
    r"(?P<value>[A-ZА-ЯӘҒҚҢӨҰҮҺІ0-9][\w./-]{1,})"
)
DOC_ID_NUMERIC_PATTERN = re.compile(
    r"(?i)\b(?:договор|контракт|приказ|акт|сч[её]т)\b[ \t]*"
    r"(?P<value>\d[\w./-]{1,})"
)

TEXT_PATTERNS: tuple[TextPattern, ...] = (
    TextPattern("personal", "EMAIL", re.compile(r"(?<![\w.-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w.-])", re.I), 0.98, 90),
    TextPattern(
        "personal",
        "PHONE",
        re.compile(r"(?<!\d)(?:\+?7|8)[\s()\-]*\d{3}[\s()\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)"),
        0.96,
        90,
    ),
    TextPattern("personal", "ADDRESS", ADDRESS_LABEL_PATTERN, 0.94, 85, "value"),
    TextPattern("personal", "ADDRESS", ADDRESS_LINE_PATTERN, 0.86, 85, "value"),
    TextPattern("personal", "PERSON", PERSON_LABEL_CONTEXT_PATTERN, 0.9, 60, "value"),
    TextPattern("personal", "PERSON", PERSON_FULL_LABEL_PATTERN, 0.9, 60, "value"),
    TextPattern("personal", "PERSON", PERSON_ROLE_CONTEXT_PATTERN, 0.88, 60, "value"),
    TextPattern("financial", "IBAN", re.compile(r"\bKZ\d{2}[A-Z0-9]{16}\b", re.I), 0.98, 90),
    TextPattern(
        "financial",
        "AMOUNT",
        re.compile(
            r"(?<!\w)\d[\d\s]*(?:[.,]\d+)?\s*"
            r"(?:(?:₸|₽|\$|€)(?!\w)|(?:тенге|руб(?:лей|ля)?|KZT|RUB|USD|EUR)\b)",
            re.I,
        ),
        0.95,
        80,
    ),
    TextPattern(
        "context",
        "DATE",
        re.compile(
            r"(?<!\d)(?:0?[1-9]|[12]\d|3[01])[./-]"
            r"(?:0?[1-9]|1[0-2])[./-](?:19|20)\d{2}(?!\d)"
        ),
        0.9,
        50,
    ),
    TextPattern("service", "DOC_ID", DOC_ID_MARKED_PATTERN, 0.94, 75, "value"),
    TextPattern("service", "DOC_ID", DOC_ID_NUMERIC_PATTERN, 0.9, 75, "value"),
    TextPattern("service", "ORG", ORG_FORM_PREFIX_PATTERN, 0.92, 70, "value"),
    TextPattern("service", "ORG", ORG_FORM_SUFFIX_PATTERN, 0.92, 70, "value"),
    TextPattern("service", "ORG", ORG_FULL_FORM_PATTERN, 0.92, 70, "value"),
    TextPattern("service", "ORG", ORG_RU_BODY_PATTERN, 0.86, 70, "value"),
    TextPattern("service", "ORG", ORG_RU_LOCATION_PATTERN, 0.86, 70, "value"),
    TextPattern("service", "ORG", ORG_KK_BODY_PATTERN, 0.86, 70, "value"),
    TextPattern("service", "ORG", ORG_KK_LOCATION_PATTERN, 0.86, 70, "value"),
)

IIN_LABEL_PATTERN = re.compile(
    r"(?i)(?:ИИН|ЖСН|IIN|индивидуальный\s+идентификационный\s+номер|"
    r"жеке\s+сәйкестендіру\s+нөмірі)\s*[:№#-]?\s*(?P<value>\d(?:[ \t-]?\d){11})(?!\d)"
)
BIN_LABEL_PATTERN = re.compile(
    r"(?i)(?:БИН|БСН|BIN|бизнес-идентификационный\s+номер|"
    r"бизнес-сәйкестендіру\s+нөмірі)\s*[:№#-]?\s*(?P<value>\d(?:[ \t-]?\d){11})(?!\d)"
)
COMBINED_ID_LABEL_PATTERN = re.compile(
    r"(?i)(?:ИИН\s*/\s*БИН|ЖСН\s*/\s*БСН|ИИН\s*\(БИН\)|ЖСН\s*\(БСН\))"
    r"\s*[:№#-]?\s*(?P<value>\d(?:[ \t-]?\d){11})(?!\d)"
)
BARE_ID_PATTERN = re.compile(r"(?<!\d)(?P<value>\d{12})(?!\d)")

PERSON_STOP_PHRASES = {
    "акционерное общество",
    "общие положения",
    "республика казахстан",
    "северный казахстан",
    "физическое лицо",
    "заңды тұлға",
}


def find_text_candidates(text: str, categories: set[str]) -> list[TextCandidate]:
    """Find high-signal entities and resolve textual overlaps before PDF mapping."""
    candidates: list[TextCandidate] = []
    for spec in TEXT_PATTERNS:
        if spec.group not in categories:
            continue
        for match in spec.pattern.finditer(text):
            start, end = match.span(spec.value_group)
            raw_value = match.group(spec.value_group)
            leading_space = len(raw_value) - len(raw_value.lstrip())
            value = raw_value.strip()
            start += leading_space
            end = start + len(value)
            if not value:
                continue
            if spec.category == "PERSON" and value.casefold() in PERSON_STOP_PHRASES:
                continue
            if spec.category == "ADDRESS":
                value = _trim_address_suffix(value)
                end = start + len(value)
            if spec.category == "ADDRESS" and not _looks_like_address(value):
                continue
            candidates.append(
                TextCandidate(
                    group=spec.group,
                    category=spec.category,
                    text=value,
                    start=start,
                    end=end,
                    confidence=spec.confidence,
                    priority=spec.priority,
                )
            )
    candidates.extend(_identifier_candidates(text, categories))
    return _resolve_text_overlaps(candidates)


def validate_kz_identifier(value: str) -> bool:
    """Validate the official two-pass modulo-11 control digit."""
    digits = _digits_only(value)
    if len(digits) != 12 or len(set(digits)) == 1:
        return False
    values = [int(character) for character in digits]
    checksum = sum(value * weight for value, weight in zip(values[:11], range(1, 12))) % 11
    if checksum == 10:
        second_weights = (3, 4, 5, 6, 7, 8, 9, 10, 11, 1, 2)
        checksum = sum(value * weight for value, weight in zip(values[:11], second_weights)) % 11
    return checksum != 10 and checksum == values[11]


def classify_kz_identifier(value: str) -> str | None:
    digits = _digits_only(value)
    if not validate_kz_identifier(digits):
        return None
    # Current BIN rules reserve the fifth digit outside 0..3 and encode YYMM
    # in the first four digits. This is safer than the obsolete "7th digit"
    # shortcut sometimes used for legacy IINs.
    month = int(digits[2:4])
    if 1 <= month <= 12 and digits[4] not in "0123":
        return "BIN"
    return "IIN"


def _identifier_candidates(text: str, categories: set[str]) -> list[TextCandidate]:
    candidates: list[TextCandidate] = []
    labeled = (
        ("personal", "IIN", IIN_LABEL_PATTERN),
        ("service", "BIN", BIN_LABEL_PATTERN),
    )
    for group, category, pattern in labeled:
        if group not in categories:
            continue
        for match in pattern.finditer(text):
            value = match.group("value")
            candidates.append(
                TextCandidate(
                    group=group,
                    category=category,
                    text=value,
                    start=match.start("value"),
                    end=match.end("value"),
                    confidence=0.99 if validate_kz_identifier(value) else 0.86,
                    priority=100,
                )
            )

    if categories & {"personal", "service"}:
        for match in COMBINED_ID_LABEL_PATTERN.finditer(text):
            value = match.group("value")
            detected = classify_kz_identifier(value)
            category = detected or "IIN_OR_BIN"
            group = "service" if category == "BIN" else "personal"
            if group not in categories:
                group = "personal" if "personal" in categories else "service"
                category = "IIN_OR_BIN"
            candidates.append(
                TextCandidate(
                    group=group,
                    category=category,
                    text=value,
                    start=match.start("value"),
                    end=match.end("value"),
                    confidence=0.99 if detected else 0.86,
                    priority=100,
                )
            )

        for match in BARE_ID_PATTERN.finditer(text):
            value = match.group("value")
            category = classify_kz_identifier(value)
            if category is None:
                continue
            group = "service" if category == "BIN" else "personal"
            if group not in categories:
                continue
            candidates.append(
                TextCandidate(
                    group=group,
                    category=category,
                    text=value,
                    start=match.start("value"),
                    end=match.end("value"),
                    confidence=0.9 if category == "BIN" else 0.84,
                    priority=95,
                )
            )
    return candidates


def _resolve_text_overlaps(candidates: list[TextCandidate]) -> list[TextCandidate]:
    accepted: list[TextCandidate] = []
    for candidate in sorted(
        candidates,
        key=lambda item: (-item.priority, -item.confidence, -(item.end - item.start), item.start),
    ):
        if any(candidate.start < other.end and other.start < candidate.end for other in accepted):
            continue
        accepted.append(candidate)
    return sorted(accepted, key=lambda item: (item.start, item.end))


def _digits_only(value: str) -> str:
    return "".join(character for character in value if "0" <= character <= "9")


def _looks_like_address(value: str) -> bool:
    if re.fullmatch(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+\.?", value, re.I):
        return False
    return bool(
        re.search(r"\d", value)
        or re.search(
            r"(?i)\b(?:ул(?:ица)?|көшесі|к-сі|проспект|пр-т|даңғылы|мкр|микрорайон|"
            r"дом|үй|квартира|пәтер|офис|кеңсе)\b",
            value,
        )
    )


def _trim_address_suffix(value: str) -> str:
    suffix = re.search(
        r"(?:,\s*|\s{2,})(?:(?i:тел(?:ефон)?|phone|e-?mail|электрон(?:дық|ная)\s+"
        r"(?:пошта|почта))|(?:ТОО|ЖШС|АО|АҚ|ГУ|ММ|КГУ|КММ|РГУ|РММ))\b",
        value,
    )
    if suffix and suffix.start() >= 3:
        return value[: suffix.start()].rstrip(" ,")
    return value


def detect_redactions(
    source: Path,
    categories: set[str],
    progress=None,
) -> tuple[list[dict], dict]:
    from app.services.privacy_detection import PRIVACY_ENGINE_VERSION, PrivacyEngine

    findings: list[dict] = []
    failures: list[dict] = []
    coverage_pages: list[dict] = []
    native_text_pages = 0
    ocr_pages = 0
    engine = PrivacyEngine()
    try:
        with pymupdf.open(source) as document:
            if document.needs_pass:
                raise RedactionError("Password-protected PDFs are not supported")
            page_count = document.page_count
            for page_index, page in enumerate(document):
                page_number = page_index + 1
                page_failures: list[dict] = []
                layers: list[PageTextLayer] = []
                try:
                    native_words, native_text = _native_page_words(page)
                    if native_words:
                        native_text_pages += 1
                        layers.append(PageTextLayer("native", native_words, native_text))
                except Exception as error:
                    native_text = ""
                    page_failures.append(
                        _detector_failure(page_number, "native_text", error)
                    )

                try:
                    ocr_required = _page_requires_ocr(page, native_text)
                except Exception as error:
                    # If image inspection fails, OCR is the safer fallback and the
                    # inspection failure remains visible in coverage metadata.
                    ocr_required = True
                    page_failures.append(
                        _detector_failure(page_number, "image_inspection", error)
                    )
                ocr_status = "not_required"
                if ocr_required:
                    try:
                        ocr_words, ocr_text, ocr_confidence = _ocr_page_words(page)
                        if not ocr_words and _page_has_visible_content(page):
                            raise RedactionError(
                                "OCR returned no readable text for a non-empty page"
                            )
                        layers.append(
                            PageTextLayer(
                                "ocr",
                                ocr_words,
                                ocr_text,
                                confidence=ocr_confidence,
                            )
                        )
                        ocr_pages += 1
                        ocr_status = "checked"
                    except Exception as error:
                        ocr_status = "failed"
                        page_failures.append(
                            _detector_failure(page_number, "ocr", error)
                        )

                detectors: set[str] = set()
                for layer in layers:
                    detection = engine.detect_text(
                        layer.text,
                        categories,
                        include_ner=True,
                        fail_closed=False,
                    )
                    detectors.update(detection.detectors)
                    for failure in detection.failures:
                        item = failure.as_dict()
                        item.update({"page": page_number, "source": layer.source})
                        page_failures.append(item)
                    for candidate in detection.spans:
                        rect = _span_rect(layer.words, candidate.start, candidate.end)
                        if rect is None:
                            page_failures.append(
                                {
                                    "page": page_number,
                                    "detector": "coordinate_mapping",
                                    "source": layer.source,
                                    "category": candidate.category,
                                    "message": "Detected text could not be mapped to PDF coordinates",
                                }
                            )
                            continue
                        confidence = candidate.confidence
                        if layer.confidence is not None:
                            confidence = min(confidence, max(layer.confidence, 1) / 100)
                        findings.append(
                            _finding(
                                page_number,
                                candidate.group,
                                candidate.category,
                                candidate.text,
                                rect,
                                page.rect,
                                confidence=confidence,
                                source=layer.source,
                                recognizer=candidate.recognizer,
                                review_required=(
                                    candidate.review_required
                                    or layer.source == "ocr"
                                    or confidence < 0.9
                                ),
                            )
                        )

                visual_status = "not_requested"
                if "visual" in categories:
                    try:
                        visual_findings, visual_failures, visual_detectors = (
                            _visual_findings(page, page_number)
                        )
                        findings.extend(visual_findings)
                        page_failures.extend(visual_failures)
                        detectors.update(visual_detectors)
                        visual_status = "partial" if visual_failures else "checked"
                    except Exception as error:
                        visual_status = "failed"
                        page_failures.append(
                            _detector_failure(page_number, "visual", error)
                        )
                page_failures = _deduplicate_failures(page_failures)
                failures.extend(page_failures)
                coverage_pages.append(
                    {
                        "page": page_number,
                        "complete": not page_failures,
                        "native_text": bool(native_text),
                        "ocr_required": ocr_required,
                        "ocr_status": ocr_status,
                        "visual_status": visual_status,
                        "detectors": sorted(detectors),
                    }
                )
                if progress:
                    progress(
                        10 + int(((page_index + 1) / max(page_count, 1)) * 80),
                        "detecting",
                    )
    except RedactionError:
        raise
    except Exception as error:
        raise RedactionError("Unable to inspect the PDF") from error
    findings = _deduplicate(findings)
    for index, finding in enumerate(findings, start=1):
        finding["id"] = f"finding-{index}"
    checked_pages = [item["page"] for item in coverage_pages if item["complete"]]
    unchecked_pages = [item["page"] for item in coverage_pages if not item["complete"]]
    return findings, {
        "page_count": page_count,
        "finding_count": len(findings),
        "categories": sorted(categories),
        "requires_confirmation": True,
        "automatic_detection": True,
        "local_only": True,
        "engine_version": PRIVACY_ENGINE_VERSION,
        "native_text_page_count": native_text_pages,
        "ocr_page_count": ocr_pages,
        "detector_failures": _deduplicate_failures(failures),
        "coverage": {
            "complete": not unchecked_pages,
            "checked_pages": checked_pages,
            "unchecked_pages": unchecked_pages,
            "pages": coverage_pages,
        },
    }


def apply_redactions(
    source: Path,
    destination: Path,
    findings: list[dict],
    selected_ids: set[str],
    mode: str,
    progress=None,
) -> dict:
    selected = [finding for finding in findings if finding["id"] in selected_ids]
    if not selected:
        raise RedactionError("Select at least one finding")
    if mode not in {"black", "pseudonymize"}:
        raise RedactionError("Unknown redaction mode")
    by_page: dict[int, list[dict]] = defaultdict(list)
    for finding in selected:
        by_page[int(finding["page"])].append(finding)
    replacements = _replacement_map(selected)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with pymupdf.open(source) as document:
            for completed, (page_number, page_findings) in enumerate(sorted(by_page.items()), start=1):
                page = document.load_page(page_number - 1)
                for finding in page_findings:
                    rect = pymupdf.Rect(*finding["pdf_rect"])
                    fill = (0, 0, 0) if mode == "black" else (1, 1, 1)
                    page.add_redact_annot(rect, fill=fill, cross_out=False)
                page.apply_redactions(images=2, graphics=2, text=0)
                if mode == "pseudonymize":
                    for finding in page_findings:
                        rect = pymupdf.Rect(*finding["pdf_rect"])
                        _insert_replacement(page, rect, replacements[finding["id"]])
                if progress:
                    progress(15 + int((completed / len(by_page)) * 65), "redacting")
            if progress:
                progress(85, "sanitizing")
            _remove_interactive_content(document)
            document.scrub(
                attached_files=True,
                clean_pages=True,
                embedded_files=True,
                hidden_text=True,
                javascript=True,
                metadata=True,
                redactions=False,
                remove_links=True,
                reset_fields=True,
                reset_responses=True,
                thumbnails=True,
                xml_metadata=True,
            )
            flatten_meta = _save_flattened_pdf(document, destination, progress)
        with pymupdf.open(destination) as check:
            if check.page_count < 1:
                raise RedactionError("The redacted PDF is invalid")
    except RedactionError:
        destination.unlink(missing_ok=True)
        raise
    except Exception as error:
        destination.unlink(missing_ok=True)
        raise RedactionError("Unable to apply redactions safely") from error
    if progress:
        progress(100, "completed")
    return {
        "mode": mode,
        "redacted_count": len(selected),
        "sanitized": True,
        "flattened": True,
        "selectable_text": False,
        "render_dpi": flatten_meta["render_dpi"],
        "image_format": "jpeg",
        "jpeg_quality": flatten_meta["jpeg_quality"],
        "manual_confirmation": True,
    }


def _remove_interactive_content(document) -> None:
    """Remove structures which can retain PII outside visible page content."""
    document.set_toc([])
    for page_number in range(document.page_count):
        page = document.load_page(page_number)
        while page.first_annot is not None:
            page.delete_annot(page.first_annot)
        while page.first_widget is not None:
            page.delete_widget(page.first_widget)


def _save_flattened_pdf(document, destination: Path, progress=None) -> dict:
    """Rebuild from pixels and keep the result within the provider PDF limit."""
    for dpi, jpeg_quality in PROTECTED_PDF_RENDER_PROFILES:
        _render_flattened_pdf(
            document,
            destination,
            dpi=dpi,
            jpeg_quality=jpeg_quality,
            progress=progress,
        )
        if destination.stat().st_size <= settings.ai_max_pdf_bytes:
            return {"render_dpi": dpi, "jpeg_quality": jpeg_quality}
        destination.unlink(missing_ok=True)
    raise RedactionError(
        "Protected PDF exceeds the configured AI upload limit after safe compression"
    )


def _render_flattened_pdf(
    document,
    destination: Path,
    *,
    dpi: int,
    jpeg_quality: int,
    progress=None,
) -> None:
    flattened = pymupdf.open()
    try:
        page_count = document.page_count
        for page_index, page in enumerate(document):
            pixmap = page.get_pixmap(
                dpi=dpi,
                alpha=False,
                annots=False,
            )
            image = pixmap.tobytes(
                "jpeg",
                jpg_quality=jpeg_quality,
            )
            target = flattened.new_page(
                width=page.rect.width,
                height=page.rect.height,
            )
            target.insert_image(target.rect, stream=image)
            if progress:
                progress(
                    85 + int(((page_index + 1) / max(page_count, 1)) * 10),
                    "flattening",
                )
        flattened.save(
            destination,
            garbage=4,
            clean=True,
            deflate=True,
            deflate_images=True,
            use_objstms=1,
        )
    finally:
        flattened.close()


def findings_from_areas(source: Path, findings: list[dict], areas: list[dict]) -> list[dict]:
    """Convert UI percentage rectangles to PDF coordinates for final redaction."""
    existing = {finding["id"]: finding for finding in findings}
    resolved: list[dict] = []
    try:
        with pymupdf.open(source) as document:
            for area in areas:
                page_number = int(area["page"])
                if page_number < 1 or page_number > document.page_count:
                    raise RedactionError("Invalid redaction page")
                page_rect = document.load_page(page_number - 1).rect
                ui_rect = area["rect"]
                x0 = page_rect.x0 + page_rect.width * float(ui_rect["x"]) / 100
                y0 = page_rect.y0 + page_rect.height * float(ui_rect["y"]) / 100
                x1 = min(page_rect.x1, x0 + page_rect.width * float(ui_rect["width"]) / 100)
                y1 = min(page_rect.y1, y0 + page_rect.height * float(ui_rect["height"]) / 100)
                base = existing.get(area["id"], {})
                finding = _finding(
                    page_number,
                    base.get("group", "personal"),
                    base.get("category", "MANUAL"),
                    base.get("text", ""),
                    pymupdf.Rect(x0, y0, x1, y1),
                    page_rect,
                    float(base.get("confidence", 1)),
                )
                finding["id"] = area["id"]
                resolved.append(finding)
    except RedactionError:
        raise
    except Exception as error:
        raise RedactionError("Unable to resolve redaction areas") from error
    return resolved


def _page_words(page) -> tuple[list[dict], str]:
    items, text = _native_page_words(page)
    if items:
        return items, text
    items, text, _ = _ocr_page_words(page)
    return items, text


def _native_page_words(page) -> tuple[list[dict], str]:
    items: list[dict] = []
    parts: list[str] = []
    cursor = 0
    previous_line = None
    for raw in page.get_text("words", sort=True):
        word = str(raw[4])
        if not word:
            continue
        current_line = (raw[5], raw[6])
        if parts:
            separator = "\n" if previous_line != current_line else " "
            parts.append(separator)
            cursor += 1
        start = cursor
        parts.append(word)
        cursor += len(word)
        items.append({"start": start, "end": cursor, "rect": pymupdf.Rect(raw[:4])})
        previous_line = current_line
    return items, "".join(parts)


def _ocr_page_words(page) -> tuple[list[dict], str, float | None]:
    import pytesseract
    from pytesseract import Output

    dpi = _privacy_ocr_dpi(page)
    scale = dpi / 72
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
    image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
        pixmap.height, pixmap.width, pixmap.n
    )[:, :, :3]
    data = pytesseract.image_to_data(
        image,
        lang=settings.ocr_languages,
        config="--oem 1 --psm 3 -c preserve_interword_spaces=1",
        output_type=Output.DICT,
        timeout=settings.ocr_page_timeout_seconds,
    )
    items: list[dict] = []
    parts: list[str] = []
    confidences: list[float] = []
    cursor = 0
    previous_line = None
    values = data.get("text", [])
    for index, value in enumerate(values):
        word = str(value).strip()
        try:
            confidence = float(data["conf"][index])
        except (KeyError, TypeError, ValueError):
            confidence = -1
        # Keep low-confidence tokens for privacy recall. They remain marked for
        # human review through the layer confidence in the resulting finding.
        if not word or confidence < 0:
            continue
        current_line = (
            data.get("block_num", [0] * len(values))[index],
            data.get("par_num", [0] * len(values))[index],
            data.get("line_num", [0] * len(values))[index],
        )
        if parts:
            separator = "\n" if previous_line != current_line else " "
            parts.append(separator)
            cursor += 1
        start = cursor
        parts.append(word)
        cursor += len(word)
        x = float(data["left"][index]) / scale
        y = float(data["top"][index]) / scale
        width = float(data["width"][index]) / scale
        height = float(data["height"][index]) / scale
        items.append(
            {
                "start": start,
                "end": cursor,
                "rect": pymupdf.Rect(x, y, x + width, y + height),
                "confidence": confidence,
            }
        )
        confidences.append(confidence)
        previous_line = current_line
    mean_confidence = sum(confidences) / len(confidences) if confidences else None
    return items, "".join(parts), mean_confidence


def _page_requires_ocr(page, native_text: str) -> bool:
    signal = sum(character.isalnum() for character in native_text)
    if signal < settings.ocr_min_text_signal_chars:
        return True
    page_area = max(page.rect.get_area(), 1)
    for image in page.get_image_info(xrefs=True):
        bbox = pymupdf.Rect(image.get("bbox", (0, 0, 0, 0)))
        if bbox.get_area() / page_area >= 0.01:
            return True
    return False


def _page_has_visible_content(page) -> bool:
    pixmap = page.get_pixmap(dpi=72, alpha=False, annots=False)
    samples = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
        pixmap.height,
        pixmap.width,
        pixmap.n,
    )[:, :, :3]
    non_white = int(np.count_nonzero(np.min(samples, axis=2) < 245))
    threshold = max(16, int(pixmap.width * pixmap.height * 0.00002))
    return non_white >= threshold


def _privacy_ocr_dpi(page) -> int:
    requested = settings.ocr_render_dpi
    pixels = page.rect.width * requested / 72 * page.rect.height * requested / 72
    if pixels <= settings.ocr_max_pixels_per_page:
        return requested
    limited = math.floor(
        72
        * math.sqrt(
            settings.ocr_max_pixels_per_page
            / max(page.rect.width * page.rect.height, 1)
        )
    )
    if limited < settings.ocr_min_render_dpi:
        raise RedactionError(
            "Page exceeds the privacy OCR pixel limit at the minimum DPI"
        )
    return limited


def _span_rect(words: list[dict], start: int, end: int):
    matched = [word["rect"] for word in words if word["start"] < end and word["end"] > start]
    if not matched:
        return None
    rect = pymupdf.Rect(matched[0])
    for candidate in matched[1:]:
        rect |= candidate
    return rect + (-1.5, -1.5, 1.5, 1.5)


def _detector_failure(page_number: int, detector: str, error: Exception) -> dict:
    message = str(error).strip() or error.__class__.__name__
    return {
        "page": page_number,
        "detector": detector,
        "message": message[:240],
    }


def _deduplicate_failures(failures: list[dict]) -> list[dict]:
    result: list[dict] = []
    seen: set[tuple] = set()
    for failure in failures:
        key = (
            failure.get("page"),
            failure.get("detector"),
            failure.get("language"),
            failure.get("source"),
            failure.get("category"),
            failure.get("message"),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(failure)
    return result


def _visual_findings(page, page_number: int) -> tuple[list[dict], list[dict], list[str]]:
    import cv2

    scale = 150 / 72
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
    image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
        pixmap.height, pixmap.width, pixmap.n
    )
    rgb = image[:, :, :3]
    findings: list[dict] = []
    failures: list[dict] = []
    detectors: list[str] = []

    visual_detectors = (
        ("opencv-face", lambda: _face_findings(cv2, page, page_number, rgb, scale)),
        (
            "opencv-seal-signature",
            lambda: _seal_signature_findings(cv2, page, page_number, rgb, scale),
        ),
        ("opencv-qr", lambda: _qr_findings(cv2, page, page_number, rgb, scale)),
        (
            "opencv-barcode",
            lambda: _barcode_findings(cv2, page, page_number, rgb, scale),
        ),
    )
    for detector, run in visual_detectors:
        try:
            findings.extend(run())
            detectors.append(detector)
        except Exception as error:
            failures.append(_detector_failure(page_number, detector, error))
    return findings, failures, detectors


def _face_findings(cv2, page, page_number: int, rgb, scale: float) -> list[dict]:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    cascade_path = str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
    cascade = cv2.CascadeClassifier(cascade_path)
    if cascade.empty():
        raise RedactionError("Local face detector could not be loaded")
    findings: list[dict] = []
    for x, y, width, height in cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(28, 28),
    ):
        findings.append(
            _visual_finding(
                page,
                page_number,
                "FACE",
                x,
                y,
                width,
                height,
                scale,
                0.86,
            )
        )
    return findings


def _seal_signature_findings(
    cv2,
    page,
    page_number: int,
    rgb,
    scale: float,
) -> list[dict]:
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    blue = cv2.inRange(hsv, np.array([85, 45, 35]), np.array([140, 255, 255]))
    red = cv2.inRange(hsv, np.array([0, 55, 40]), np.array([12, 255, 255])) | cv2.inRange(
        hsv, np.array([165, 55, 40]), np.array([179, 255, 255])
    )
    mask = cv2.morphologyEx(blue | red, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    findings: list[dict] = []
    for contour in cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, width, height = cv2.boundingRect(contour)
        area = width * height
        if area < 900 or width < 25 or height < 12:
            continue
        ratio = width / max(height, 1)
        category = "SEAL" if 0.65 <= ratio <= 1.55 and area >= 1800 else "SIGNATURE"
        findings.append(
            _visual_finding(page, page_number, category, x, y, width, height, scale, 0.7)
        )
    return findings


def _qr_findings(cv2, page, page_number: int, rgb, scale: float) -> list[dict]:
    detector = cv2.QRCodeDetector()
    detected, points = detector.detectMulti(rgb)
    if not detected or points is None:
        return []
    return [
        _polygon_visual_finding(
            page,
            page_number,
            "QR_CODE",
            polygon,
            scale,
            confidence=0.95,
        )
        for polygon in points
    ]


def _barcode_findings(cv2, page, page_number: int, rgb, scale: float) -> list[dict]:
    detector_class = getattr(cv2, "barcode_BarcodeDetector", None)
    if detector_class is None:
        raise RedactionError("Local barcode detector is unavailable")
    detected, points = detector_class().detectMulti(rgb)
    if not detected or points is None:
        return []
    return [
        _polygon_visual_finding(
            page,
            page_number,
            "BARCODE",
            polygon,
            scale,
            confidence=0.9,
        )
        for polygon in points
    ]


def _polygon_visual_finding(
    page,
    page_number: int,
    category: str,
    points,
    scale: float,
    confidence: float,
) -> dict:
    polygon = np.asarray(points, dtype=float).reshape(-1, 2)
    if len(polygon) < 4 or not np.isfinite(polygon).all():
        raise RedactionError(f"{category} detector returned invalid coordinates")
    x0, y0 = polygon.min(axis=0)
    x1, y1 = polygon.max(axis=0)
    padding = 3
    return _visual_finding(
        page,
        page_number,
        category,
        max(0, x0 - padding),
        max(0, y0 - padding),
        x1 - x0 + padding * 2,
        y1 - y0 + padding * 2,
        scale,
        confidence,
    )


def _visual_finding(page, page_number, category, x, y, width, height, scale, confidence):
    rect = pymupdf.Rect(x / scale, y / scale, (x + width) / scale, (y + height) / scale)
    return _finding(
        page_number,
        "visual",
        category,
        "",
        rect,
        page.rect,
        confidence,
        source="visual",
        review_required=True,
    )


def _finding(
    page_number,
    group,
    category,
    text,
    rect,
    page_rect,
    confidence,
    *,
    source="manual",
    recognizer="",
    review_required=False,
):
    finding = {
        "id": "",
        "page": page_number,
        "group": group,
        "category": category,
        "text": text.strip(),
        "confidence": round(confidence, 2),
        "pdf_rect": [round(rect.x0, 2), round(rect.y0, 2), round(rect.x1, 2), round(rect.y1, 2)],
        "rect": {
            "x": round(rect.x0 / page_rect.width * 100, 3),
            "y": round(rect.y0 / page_rect.height * 100, 3),
            "width": round(rect.width / page_rect.width * 100, 3),
            "height": round(rect.height / page_rect.height * 100, 3),
        },
    }
    finding["source"] = source
    finding["review_required"] = bool(review_required)
    if recognizer:
        finding["recognizer"] = recognizer
    return finding


def _deduplicate(findings: list[dict]) -> list[dict]:
    from app.services.privacy_detection import PRIVACY_TAXONOMY

    result: list[dict] = []
    priority = {
        category: spec.priority for category, spec in PRIVACY_TAXONOMY.items()
    }
    ordered = sorted(
        findings,
        key=lambda item: (
            item["page"],
            -priority.get(item["category"], 0),
            -item["confidence"],
            item["pdf_rect"][1],
            item["pdf_rect"][0],
        ),
    )
    for finding in ordered:
        rect = pymupdf.Rect(*finding["pdf_rect"])
        duplicate = False
        for accepted in result:
            if accepted["page"] != finding["page"]:
                continue
            other = pymupdf.Rect(*accepted["pdf_rect"])
            intersection = rect & other
            if intersection.get_area() / max(min(rect.get_area(), other.get_area()), 1) > 0.75:
                duplicate = True
                accepted_rank = (priority.get(accepted["category"], 0), accepted["confidence"])
                finding_rank = (priority.get(finding["category"], 0), finding["confidence"])
                if finding_rank > accepted_rank:
                    accepted.update(finding)
                break
        if not duplicate:
            result.append(finding)
    return sorted(result, key=lambda item: (item["page"], item["pdf_rect"][1], item["pdf_rect"][0]))


def _replacement_map(findings: list[dict]) -> dict[str, str]:
    counters: dict[str, int] = defaultdict(int)
    values: dict[tuple[str, str], str] = {}
    result: dict[str, str] = {}
    labels = {
        "PERSON": "Гражданин",
        "ADDRESS": "Адрес",
        "ORG": "Организация",
        "IIN": "ИИН скрыт",
        "IIN_OR_BIN": "ИИН/БИН скрыт",
        "QR_CODE": "QR-код скрыт",
        "BARCODE": "Штрихкод скрыт",
        "PAYMENT_CARD": "Карта скрыта",
        "EMAIL": "Email скрыт",
        "PHONE": "Телефон скрыт",
        "IBAN": "Счёт скрыт",
        "AMOUNT": "Сумма скрыта",
        "BIN": "БИН скрыт",
        "DOC_ID": "Номер скрыт",
        "FACE": "Лицо скрыто",
        "SEAL": "Печать скрыта",
        "SIGNATURE": "Подпись скрыта",
        "LOCATION": "Место скрыто",
        "DATE": "Дата скрыта",
    }
    for finding in findings:
        category = finding["category"]
        key = category, finding.get("text", "").strip().casefold() or finding["id"]
        if key not in values:
            counters[category] += 1
            suffix = _alpha(counters[category]) if category in {"PERSON", "ADDRESS", "ORG"} else ""
            values[key] = f"{labels.get(category, 'Скрыто')} {suffix}".strip()
        result[finding["id"]] = values[key]
    return result


def _alpha(index: int) -> str:
    letters = string.ascii_uppercase
    result = ""
    while index > 0:
        index, remainder = divmod(index - 1, len(letters))
        result = letters[remainder] + result
    return result


def _insert_replacement(page, rect, text: str) -> None:
    font = _font_path()
    font_size = max(5, min(10, rect.height * 0.6))
    kwargs = {"fontname": "redaction-font", "fontfile": str(font)} if font else {"fontname": "helv"}
    result = page.insert_textbox(
        rect,
        text,
        fontsize=font_size,
        color=(0, 0, 0),
        fill=(1, 1, 1),
        align=0,
        overlay=True,
        **kwargs,
    )
    if result < 0:
        page.insert_textbox(
            rect,
            "СКРЫТО" if font else "REDACTED",
            fontsize=max(4, font_size - 2),
            color=(0, 0, 0),
            overlay=True,
            **kwargs,
        )


def _font_path() -> Path | None:
    candidates = (
        Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    )
    return next((path for path in candidates if path.is_file()), None)
