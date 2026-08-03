from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import re
import string

import numpy as np
import pymupdf

from app.core.config import settings


class RedactionError(RuntimeError):
    pass


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
        re.compile(r"(?<!\w)\d[\d\s]*(?:[.,]\d+)?\s*(?:₸|₽|\$|€|тенге|KZT|RUB|USD|EUR)\b", re.I),
        0.95,
        80,
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
    findings: list[dict] = []
    try:
        with pymupdf.open(source) as document:
            if document.needs_pass:
                raise RedactionError("Password-protected PDFs are not supported")
            page_count = document.page_count
            for page_index, page in enumerate(document):
                words, text = _page_words(page)
                for candidate in find_text_candidates(text, categories):
                    rect = _span_rect(words, candidate.start, candidate.end)
                    if rect is None:
                        continue
                    findings.append(
                        _finding(
                            page_index + 1,
                            candidate.group,
                            candidate.category,
                            candidate.text,
                            rect,
                            page.rect,
                            confidence=candidate.confidence,
                        )
                    )
                if "visual" in categories:
                    findings.extend(_visual_findings(page, page_index + 1))
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
    return findings, {
        "page_count": page_count,
        "finding_count": len(findings),
        "categories": sorted(categories),
        "requires_confirmation": True,
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
            document.save(
                destination,
                garbage=4,
                clean=True,
                deflate=True,
                deflate_images=True,
                deflate_fonts=True,
                use_objstms=1,
            )
        with pymupdf.open(destination) as check:
            if check.page_count < 1:
                raise RedactionError("The redacted PDF is invalid")
    except RedactionError:
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
        "manual_confirmation": True,
    }


def _page_words(page) -> tuple[list[dict], str]:
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
    if items:
        return items, "".join(parts)
    return _ocr_page_words(page)


def _ocr_page_words(page) -> tuple[list[dict], str]:
    try:
        import pytesseract
        from pytesseract import Output

        scale = 200 / 72
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
            pixmap.height, pixmap.width, pixmap.n
        )[:, :, :3]
        data = pytesseract.image_to_data(
            image,
            lang=settings.ocr_languages,
            output_type=Output.DICT,
            timeout=settings.ocr_page_timeout_seconds,
        )
        items: list[dict] = []
        parts: list[str] = []
        cursor = 0
        previous_line = None
        for index, value in enumerate(data.get("text", [])):
            word = str(value).strip()
            try:
                confidence = float(data["conf"][index])
            except (KeyError, TypeError, ValueError):
                confidence = -1
            if not word or confidence < 30:
                continue
            current_line = (
                data.get("block_num", [0] * len(data["text"]))[index],
                data.get("par_num", [0] * len(data["text"]))[index],
                data.get("line_num", [0] * len(data["text"]))[index],
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
                }
            )
            previous_line = current_line
        return items, "".join(parts)
    except Exception:
        return [], ""


def _span_rect(words: list[dict], start: int, end: int):
    matched = [word["rect"] for word in words if word["start"] < end and word["end"] > start]
    if not matched:
        return None
    rect = pymupdf.Rect(matched[0])
    for candidate in matched[1:]:
        rect |= candidate
    return rect + (-1.5, -1.5, 1.5, 1.5)


def _visual_findings(page, page_number: int) -> list[dict]:
    try:
        import cv2

        scale = 150 / 72
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, pixmap.n)
        rgb = image[:, :, :3]
        findings: list[dict] = []
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        cascade_path = str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
        cascade = cv2.CascadeClassifier(cascade_path)
        for x, y, width, height in cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(28, 28)):
            findings.append(_visual_finding(page, page_number, "FACE", x, y, width, height, scale, 0.86))

        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        blue = cv2.inRange(hsv, np.array([85, 45, 35]), np.array([140, 255, 255]))
        red = cv2.inRange(hsv, np.array([0, 55, 40]), np.array([12, 255, 255])) | cv2.inRange(
            hsv, np.array([165, 55, 40]), np.array([179, 255, 255])
        )
        mask = cv2.morphologyEx(blue | red, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        for contour in cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
            x, y, width, height = cv2.boundingRect(contour)
            area = width * height
            if area < 900 or width < 25 or height < 12:
                continue
            ratio = width / max(height, 1)
            category = "SEAL" if 0.65 <= ratio <= 1.55 and area >= 1800 else "SIGNATURE"
            findings.append(_visual_finding(page, page_number, category, x, y, width, height, scale, 0.7))
        return findings
    except Exception:
        return []


def _visual_finding(page, page_number, category, x, y, width, height, scale, confidence):
    rect = pymupdf.Rect(x / scale, y / scale, (x + width) / scale, (y + height) / scale)
    return _finding(page_number, "visual", category, "", rect, page.rect, confidence)


def _finding(page_number, group, category, text, rect, page_rect, confidence):
    return {
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


def _deduplicate(findings: list[dict]) -> list[dict]:
    result: list[dict] = []
    priority = {
        "IIN": 100,
        "BIN": 100,
        "IIN_OR_BIN": 95,
        "EMAIL": 90,
        "PHONE": 90,
        "IBAN": 90,
        "ADDRESS": 85,
        "AMOUNT": 80,
        "DOC_ID": 75,
        "ORG": 70,
        "PERSON": 60,
        "FACE": 55,
        "SEAL": 55,
        "SIGNATURE": 55,
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
        "EMAIL": "Email скрыт",
        "PHONE": "Телефон скрыт",
        "IBAN": "Счёт скрыт",
        "AMOUNT": "Сумма скрыта",
        "BIN": "БИН скрыт",
        "DOC_ID": "Номер скрыт",
        "FACE": "Лицо скрыто",
        "SEAL": "Печать скрыта",
        "SIGNATURE": "Подпись скрыта",
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
    return letters[(index - 1) % len(letters)]


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
