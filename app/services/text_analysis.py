from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from difflib import SequenceMatcher
import math
import re
import unicodedata
from pathlib import Path

from langdetect import LangDetectException, detect
from pypdf import PdfReader

from app.core.config import settings
from app.models.document import Document
from app.services.file_storage import resolve_stored_path

WORD_PATTERN = re.compile(r"\w+", re.UNICODE)
LETTER_TOKEN_PATTERN = re.compile(r"[^\W\d_]+", re.UNICODE)
MAX_CELL_RETRIES = 20
MAX_TARGETED_RETRIES = 12
ORGANIZATION_MARKERS = {"ао", "ao", "ип", "jsc", "llp", "тоо", "too"}
PROTECTED_LATIN_TERMS = {
    "API",
    "HTTP",
    "HTTPS",
    "JSON",
    "OCR",
    "PDF",
    "REST",
    "SQL",
    "UI",
    "URL",
    "UUID",
    "XML",
}
CYRILLIC_LATIN_CONFUSABLES = str.maketrans(
    {
        "А": "A",
        "В": "B",
        "С": "C",
        "Е": "E",
        "Н": "H",
        "І": "I",
        "К": "K",
        "М": "M",
        "О": "O",
        "Р": "P",
        "Т": "T",
        "Х": "X",
        "У": "Y",
    }
)
NUMERIC_FIELD_LABELS = {"балл", "оценка", "score"}

ProgressCallback = Callable[[int, int, str], None]


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int | None
    text: str
    extraction_method: str
    extraction_quality: str = "unknown"
    confidence: float | None = None
    table_count: int = 0
    uncertain_region_count: int = 0
    meta: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractionQualityAssessment:
    quality: str
    requires_manual_review: bool
    meta: dict


@dataclass(frozen=True)
class OCRWord:
    text: str
    confidence: float
    left: int
    top: int
    width: int
    height: int
    block: int
    paragraph: int
    line: int

    @property
    def center(self) -> tuple[float, float]:
        return (self.left + self.width / 2, self.top + self.height / 2)


@dataclass(frozen=True)
class OCRCandidate:
    text: str
    words: tuple[OCRWord, ...]
    mean_confidence: float
    low_confidence_ratio: float
    preprocessing: str

    @property
    def score(self) -> float:
        signal_bonus = min(sum(character.isalnum() for character in self.text) / 50, 5)
        return self.mean_confidence - self.low_confidence_ratio * 40 + signal_bonus


@dataclass
class DetectedCell:
    row: int
    column: int
    left: int
    top: int
    right: int
    bottom: int
    words: list[OCRWord] = field(default_factory=list)
    column_span: int = 1
    uncertain: bool = False

    @property
    def box(self) -> tuple[int, int, int, int]:
        return self.left, self.top, self.right, self.bottom


@dataclass
class DetectedTable:
    left: int
    top: int
    right: int
    bottom: int
    rows: int
    columns: int
    cells: list[DetectedCell]
    ambiguous: bool = False

    @property
    def box(self) -> tuple[int, int, int, int]:
        return self.left, self.top, self.right, self.bottom


class OCRExtractionError(ValueError):
    pass


def extract_text(document: Document) -> str:
    return join_page_text(extract_text_pages(document))


def extract_text_pages(
    document: Document,
    progress_callback: ProgressCallback | None = None,
) -> list[ExtractedPage]:
    path = resolve_stored_path(document.stored_path)
    if document.content_type != "application/pdf":
        raise ValueError("Only PDF documents can be analyzed")
    return extract_pdf_pages_with_ocr(path, progress_callback=progress_callback)


def extract_pdf_text(path: Path) -> str:
    return join_page_text(extract_pdf_pages(path, extraction_method="native"))


def extract_pdf_pages(
    path: Path,
    *,
    extraction_method: str,
) -> list[ExtractedPage]:
    pymupdf = _pymupdf()
    try:
        with pymupdf.open(path) as pdf:
            return [
                ExtractedPage(
                    page_number=index,
                    text=page.get_text("text", sort=True) or "",
                    extraction_method=extraction_method,
                    extraction_quality="high",
                )
                for index, page in enumerate(pdf, start=1)
            ]
    except Exception as error:
        raise OCRExtractionError(
            "PDF analysis failed: document is invalid or corrupted"
        ) from error


def extract_page_text(page) -> str:
    try:
        if hasattr(page, "get_text"):
            return page.get_text("text", sort=True) or ""
        return page.extract_text() or ""
    except Exception:
        return ""


def join_page_text(pages: list[ExtractedPage]) -> str:
    return "\n\n".join(page.text.strip() for page in pages if page.text.strip())


def extract_pdf_text_with_ocr(path: Path) -> str:
    return join_page_text(extract_pdf_pages_with_ocr(path))


def extract_pdf_pages_with_ocr(
    path: Path,
    progress_callback: ProgressCallback | None = None,
) -> list[ExtractedPage]:
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            raise OCRExtractionError(
                "PDF analysis failed: password-protected PDFs are not supported"
            )
        pypdf_texts = [extract_page_text(page) for page in reader.pages]
    except OCRExtractionError:
        raise
    except Exception as error:
        raise OCRExtractionError(
            "PDF analysis failed: document is invalid or corrupted"
        ) from error

    pymupdf = _pymupdf()
    try:
        pdf = pymupdf.open(path)
    except Exception as error:
        if pypdf_texts and all(_native_text_is_reliable(text) for text in pypdf_texts):
            return [
                ExtractedPage(
                    page_number=index,
                    text=text.strip(),
                    extraction_method="native",
                    extraction_quality="high",
                )
                for index, text in enumerate(pypdf_texts, start=1)
            ]
        raise OCRExtractionError(
            "PDF analysis failed: document is invalid or corrupted"
        ) from error

    try:
        if pdf.needs_pass:
            raise OCRExtractionError(
                "PDF analysis failed: password-protected PDFs are not supported"
            )
        try:
            total_pages = pdf.page_count
        except Exception:
            total_pages = 0
        if total_pages != len(pypdf_texts):
            if pypdf_texts and all(
                _native_text_is_reliable(text) for text in pypdf_texts
            ):
                return [
                    ExtractedPage(
                        page_number=index,
                        text=text.strip(),
                        extraction_method="native",
                        extraction_quality="high",
                    )
                    for index, text in enumerate(pypdf_texts, start=1)
                ]
            raise OCRExtractionError(
                "PDF analysis failed: page tree could not be rendered"
            )
        extracted_pages: list[ExtractedPage] = []
        for page_index in range(total_pages):
            page_number = page_index + 1
            if progress_callback:
                progress_callback(page_index, total_pages, "triage")
            try:
                page = pdf.load_page(page_index)
                native_text = page.get_text("text", sort=True) or ""
            except Exception:
                native_text = pypdf_texts[page_index]
                if _native_text_is_reliable(native_text):
                    extracted_pages.append(
                        ExtractedPage(
                            page_number=page_number,
                            text=native_text.strip(),
                            extraction_method="native",
                            extraction_quality="high",
                        )
                    )
                    if progress_callback:
                        progress_callback(page_number, total_pages, "pages")
                    continue
                raise OCRExtractionError(
                    f"PDF analysis failed: page {page_number} could not be rendered"
                )
            if (
                not _native_text_is_reliable(native_text)
                and _native_text_is_reliable(pypdf_texts[page_index])
            ):
                extracted_pages.append(
                    ExtractedPage(
                        page_number=page_number,
                        text=pypdf_texts[page_index].strip(),
                        extraction_method="native",
                        extraction_quality="high",
                    )
                )
                if progress_callback:
                    progress_callback(page_number, total_pages, "pages")
                continue
            if _native_text_is_reliable(native_text) and not _is_full_page_scan(page):
                extracted_pages.append(
                    ExtractedPage(
                        page_number=page_number,
                        text=native_text.strip(),
                        extraction_method="native",
                        extraction_quality="high",
                    )
                )
            else:
                if progress_callback:
                    progress_callback(page_index, total_pages, "ocr")
                extracted_pages.append(_ocr_page(page, page_number))
            if progress_callback:
                progress_callback(page_number, total_pages, "pages")
    finally:
        pdf.close()

    if not has_enough_text_signal(join_page_text(extracted_pages)):
        raise OCRExtractionError(
            "OCR failed: no readable text was found after OCR. "
            "Try a clearer scan with better lighting."
        )
    return extracted_pages


def _ocr_page(page, page_number: int) -> ExtractedPage:
    image, effective_dpi = _render_page(page)
    image = _normalize_orientation(image)
    primary_image = _preprocess_primary(image)
    primary = _run_tesseract(primary_image, "contrast")
    selected = primary
    alternate_used = False
    disagreement = False
    retry_reasons = _candidate_retry_reasons(primary)

    if retry_reasons:
        alternate = _run_tesseract(_preprocess_alternate(image), "threshold")
        alternate_used = True
        disagreement = _candidate_similarity(primary, alternate) < settings.ocr_candidate_similarity
        if alternate.score > primary.score:
            selected = alternate

    selected, latin_retry_count, latin_recovery_count = _recover_latin_spans(
        selected,
        image,
    )
    selected, numeric_retry_count, numeric_recovery_count = _recover_numeric_fields(
        selected,
        image,
    )
    tables = _detect_tables(primary_image)
    _assign_words_to_tables(tables, selected.words)
    cell_retry_count = _recover_uncertain_cells(
        tables,
        primary_image,
    )
    ambiguous_tables = sum(table.ambiguous for table in tables)
    reliable_tables = [table for table in tables if not table.ambiguous]
    uncertain_cells = sum(
        cell.uncertain for table in reliable_tables for cell in table.cells
    )
    text = _compose_page_text(selected.words, reliable_tables)
    low_word_count = sum(
        word.confidence < settings.ocr_low_word_confidence
        for word in selected.words
    )
    uncertain_count = (
        low_word_count
        + numeric_recovery_count
        + uncertain_cells
        + ambiguous_tables
        + int(disagreement)
    )
    quality = (
        "low"
        if (
            selected.mean_confidence < settings.ocr_min_mean_confidence
            or selected.low_confidence_ratio > settings.ocr_max_low_confidence_ratio
            or disagreement
            or ambiguous_tables
            or not has_enough_text_signal(text)
        )
        else "medium"
    )
    return ExtractedPage(
        page_number=page_number,
        text=text.strip(),
        extraction_method="ocr_table" if reliable_tables else "ocr",
        extraction_quality=quality,
        confidence=round(selected.mean_confidence, 2),
        table_count=len(tables),
        uncertain_region_count=uncertain_count,
        meta={
            "render_dpi": effective_dpi,
            "render_dpi_below_target_minimum": (
                effective_dpi < settings.ocr_min_render_dpi
            ),
            "preprocessing": selected.preprocessing,
            "alternate_pass_used": alternate_used,
            "retry_reasons": retry_reasons,
            "candidate_disagreement": disagreement,
            "ocr_score": round(selected.score, 2),
            "primary_ocr_score": round(primary.score, 2),
            "low_confidence_word_ratio": round(selected.low_confidence_ratio, 4),
            "latin_retry_count": latin_retry_count,
            "latin_recovery_count": latin_recovery_count,
            "numeric_retry_count": numeric_retry_count,
            "numeric_recovery_count": numeric_recovery_count,
            "cell_retry_count": cell_retry_count,
            "uncertain_cell_count": uncertain_cells,
            "ambiguous_table_count": ambiguous_tables,
        },
    )


def _pymupdf():
    try:
        import pymupdf
    except ImportError as error:
        raise OCRExtractionError("OCR failed: PyMuPDF is not installed") from error
    return pymupdf


def _cv2_and_numpy():
    try:
        import cv2
        import numpy
    except ImportError as error:
        raise OCRExtractionError(
            "OCR failed: OpenCV and NumPy are required for local OCR"
        ) from error
    return cv2, numpy


def _pytesseract():
    try:
        import pytesseract
    except ImportError as error:
        raise OCRExtractionError("OCR failed: pytesseract is not installed") from error
    return pytesseract


def _is_full_page_scan(page) -> bool:
    page_area = max(page.rect.width * page.rect.height, 1)
    try:
        for image in page.get_images(full=True):
            for rect in page.get_image_rects(image[0]):
                if rect.width * rect.height / page_area >= 0.75:
                    return True
    except Exception:
        return False
    return False


def _native_text_is_reliable(text: str) -> bool:
    if not has_enough_text_signal(text):
        return False
    visible = [character for character in text if not character.isspace()]
    if not visible:
        return False
    alphanumeric_ratio = sum(character.isalnum() for character in visible) / len(
        visible
    )
    suspicious_ratio = sum(
        _is_suspicious_character(character) for character in visible
    ) / len(visible)
    tokens = LETTER_TOKEN_PATTERN.findall(text)
    mixed_script_ratio = (
        sum(len(_token_scripts(token)) > 1 for token in tokens) / len(tokens)
        if tokens
        else 0
    )
    return (
        alphanumeric_ratio >= 0.55
        and suspicious_ratio < 0.02
        and mixed_script_ratio < 0.10
    )


def _render_page(page):
    cv2, numpy = _cv2_and_numpy()
    requested_dpi = settings.ocr_render_dpi
    page_pixels = (
        page.rect.width * requested_dpi / 72
        * page.rect.height * requested_dpi / 72
    )
    effective_dpi = requested_dpi
    if page_pixels > settings.ocr_max_pixels_per_page:
        effective_dpi = math.floor(
            72
            * math.sqrt(
                settings.ocr_max_pixels_per_page
                / (page.rect.width * page.rect.height)
            )
        )
        # Some scanners write source-image pixels directly into the PDF page box.
        # In those files even 180 "PDF DPI" needlessly upscales the source image.
        # Keep the hard pixel guard and use the highest safe DPI instead.
        effective_dpi = max(effective_dpi, 72)
        limited_pixels = (
            page.rect.width * effective_dpi / 72
            * page.rect.height * effective_dpi / 72
        )
        if limited_pixels > settings.ocr_max_pixels_per_page:
            raise OCRExtractionError(
                f"OCR failed: page exceeds the pixel limit at "
                f"{settings.ocr_min_render_dpi} DPI"
            )

    pixmap = page.get_pixmap(dpi=effective_dpi, alpha=False)
    samples = numpy.frombuffer(pixmap.samples, dtype=numpy.uint8)
    image = samples.reshape(pixmap.height, pixmap.width, pixmap.n)
    if pixmap.n == 4:
        image = cv2.cvtColor(image, cv2.COLOR_RGBA2RGB)
    elif pixmap.n == 1:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    return image, effective_dpi


def _normalize_orientation(image):
    cv2, _ = _cv2_and_numpy()
    pytesseract = _pytesseract()
    try:
        osd = pytesseract.image_to_osd(
            image,
            output_type=pytesseract.Output.DICT,
            timeout=min(settings.ocr_page_timeout_seconds, 15),
        )
        rotation = int(osd.get("rotate", 0))
        confidence = float(osd.get("orientation_conf", 0))
        if confidence >= 12 and rotation in {90, 180, 270}:
            rotations = {
                90: cv2.ROTATE_90_CLOCKWISE,
                180: cv2.ROTATE_180,
                270: cv2.ROTATE_90_COUNTERCLOCKWISE,
            }
            image = cv2.rotate(image, rotations[rotation])
    except Exception:
        pass
    return _deskew_image(image)


def _deskew_image(image):
    cv2, numpy = _cv2_and_numpy()
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    binary = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )[1]
    coordinates = numpy.column_stack(numpy.where(binary > 0))
    if len(coordinates) < 100:
        return image
    angle = cv2.minAreaRect(coordinates[:, ::-1].astype("float32"))[-1]
    angle = -(90 + angle) if angle < -45 else -angle
    if abs(angle) < 0.25 or abs(angle) > 10:
        return image
    height, width = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    return cv2.warpAffine(
        image,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )


def _preprocess_primary(image):
    cv2, _ = _cv2_and_numpy()
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    return cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)


def _preprocess_alternate(image):
    cv2, _ = _cv2_and_numpy()
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    return cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        35,
        15,
    )


def _run_tesseract(
    image,
    preprocessing: str,
    *,
    psm: int = 3,
    languages: str | None = None,
    extra_config: str = "",
) -> OCRCandidate:
    pytesseract = _pytesseract()
    config = f"--oem 1 --psm {psm} -c preserve_interword_spaces=1"
    if extra_config:
        config = f"{config} {extra_config}"
    try:
        data = pytesseract.image_to_data(
            image,
            lang=languages or settings.ocr_languages,
            config=config,
            output_type=pytesseract.Output.DICT,
            timeout=settings.ocr_page_timeout_seconds,
        )
    except pytesseract.TesseractNotFoundError as error:
        raise OCRExtractionError(
            "OCR failed: Tesseract is not installed in this environment"
        ) from error
    except RuntimeError as error:
        raise OCRExtractionError("OCR failed: Tesseract timed out") from error
    except Exception as error:
        raise OCRExtractionError(format_ocr_error(error)) from error

    words: list[OCRWord] = []
    for index, raw_text in enumerate(data.get("text", [])):
        text = str(raw_text).strip()
        try:
            confidence = float(data["conf"][index])
        except (KeyError, TypeError, ValueError):
            confidence = -1
        if not text or confidence < 0:
            continue
        words.append(
            OCRWord(
                text=text,
                confidence=confidence,
                left=int(data["left"][index]),
                top=int(data["top"][index]),
                width=int(data["width"][index]),
                height=int(data["height"][index]),
                block=int(data["block_num"][index]),
                paragraph=int(data["par_num"][index]),
                line=int(data["line_num"][index]),
            )
        )

    text = _words_to_text(words)
    if words:
        weighted_total = sum(
            word.confidence * max(len(word.text), 1) for word in words
        )
        total_weight = sum(max(len(word.text), 1) for word in words)
        mean_confidence = weighted_total / total_weight
        low_ratio = (
            sum(
                word.confidence < settings.ocr_low_word_confidence
                for word in words
            )
            / len(words)
        )
    else:
        mean_confidence = 0.0
        low_ratio = 1.0
    return OCRCandidate(
        text=text,
        words=tuple(words),
        mean_confidence=mean_confidence,
        low_confidence_ratio=low_ratio,
        preprocessing=preprocessing,
    )


def _recover_latin_spans(
    candidate: OCRCandidate,
    image,
) -> tuple[OCRCandidate, int, int]:
    if "eng" not in configured_ocr_languages():
        return candidate, 0, 0

    words = list(candidate.words)
    spans = _latin_retry_spans(words)
    replacements: dict[int, OCRWord] = {}
    removed_indices: set[int] = set()
    retries = 0
    recoveries = 0

    for indices, reason in spans[:MAX_TARGETED_RETRIES]:
        retry = _retry_word_span(
            words,
            indices,
            image,
            languages="eng",
            psm=8 if reason == "organization" else 7,
        )
        retries += 1
        core = _single_latin_core(retry.text)
        if core is None or not _accept_latin_retry(words, indices, retry, core, reason):
            continue
        replacements[indices[0]] = _replacement_word(
            words,
            indices,
            _preserve_outer_punctuation(words, indices, core),
            retry.mean_confidence,
        )
        removed_indices.update(indices[1:])
        recoveries += 1

    if not recoveries:
        return candidate, retries, 0
    recovered_words = [
        replacements.get(index, word)
        for index, word in enumerate(words)
        if index not in removed_indices
    ]
    return _candidate_from_words(recovered_words, candidate.preprocessing), retries, recoveries


def _latin_retry_spans(
    words: list[OCRWord],
) -> list[tuple[tuple[int, ...], str]]:
    lines: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    for index, word in enumerate(words):
        lines[(word.block, word.paragraph, word.line)].append(index)

    spans: list[tuple[tuple[int, ...], str]] = []
    covered: set[int] = set()
    for line_indices in lines.values():
        ordered = sorted(line_indices, key=lambda index: words[index].left)
        for position, index in enumerate(ordered[:-1]):
            marker = _letters_only(words[index].text).casefold()
            if marker not in ORGANIZATION_MARKERS:
                continue
            quoted_indices: list[int] = []
            for following_index in ordered[position + 1 : position + 5]:
                text = words[following_index].text
                if not quoted_indices and not text.startswith(("«", '"', "“", "„")):
                    break
                quoted_indices.append(following_index)
                if text.endswith(("»", '"', "”")):
                    break
            if quoted_indices and words[quoted_indices[-1]].text.endswith(
                ("»", '"', "”")
            ):
                span = tuple(quoted_indices)
                spans.append((span, "organization"))
                covered.update(span)

    for index, word in enumerate(words):
        if index in covered:
            continue
        letters = _letters_only(word.text)
        scripts = _token_scripts(letters)
        if len(scripts) > 1:
            spans.append(((index,), "mixed_script"))
            continue
        skeleton = letters.upper().translate(CYRILLIC_LATIN_CONFUSABLES)
        if (
            scripts == {"cyrillic"}
            and skeleton in PROTECTED_LATIN_TERMS
            and skeleton != letters.upper()
        ):
            spans.append(((index,), "protected_term"))
            continue
        if "?" in word.text and letters:
            spans.append(((index,), "placeholder"))
    return spans


def _recover_numeric_fields(
    candidate: OCRCandidate,
    image,
) -> tuple[OCRCandidate, int, int]:
    words = list(candidate.words)
    lines: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    for index, word in enumerate(words):
        lines[(word.block, word.paragraph, word.line)].append(index)

    replacements: dict[int, OCRWord] = {}
    retries = 0
    recoveries = 0
    for line_indices in lines.values():
        ordered = sorted(line_indices, key=lambda index: words[index].left)
        for position, index in enumerate(ordered[:-1]):
            label = _letters_only(words[index].text).casefold()
            if label not in NUMERIC_FIELD_LABELS:
                continue
            value_index = ordered[position + 1]
            original = words[value_index]
            if original.confidence >= settings.ocr_high_confidence:
                continue
            retry = _retry_word_span(
                words,
                (value_index,),
                image,
                languages="rus+eng",
                psm=8,
                margin=6,
                extra_config="-c tessedit_char_whitelist=0123456789.,/-",
            )
            retries += 1
            numeric_text = retry.text.strip()
            if (
                re.fullmatch(r"\d[\d.,/-]*", numeric_text)
                and retry.mean_confidence >= settings.ocr_low_word_confidence
                and retry.mean_confidence >= original.confidence + 10
            ):
                replacements[value_index] = _replacement_word(
                    words,
                    (value_index,),
                    numeric_text,
                    retry.mean_confidence,
                )
                recoveries += 1
            break
        if retries >= MAX_TARGETED_RETRIES:
            break

    if not recoveries:
        return candidate, retries, 0
    recovered_words = [
        replacements.get(index, word) for index, word in enumerate(words)
    ]
    return _candidate_from_words(recovered_words, candidate.preprocessing), retries, recoveries


def _retry_word_span(
    words: list[OCRWord],
    indices: tuple[int, ...],
    image,
    *,
    languages: str,
    psm: int,
    margin: int = 12,
    extra_config: str = "",
) -> OCRCandidate:
    left = max(min(words[index].left for index in indices) - margin, 0)
    top = max(min(words[index].top for index in indices) - margin, 0)
    right = min(
        max(words[index].left + words[index].width for index in indices) + margin,
        image.shape[1],
    )
    bottom = min(
        max(words[index].top + words[index].height for index in indices) + margin,
        image.shape[0],
    )
    crop = image[top:bottom, left:right]
    return _run_tesseract(
        crop,
        "targeted_retry",
        psm=psm,
        languages=languages,
        extra_config=extra_config,
    )


def _accept_latin_retry(
    words: list[OCRWord],
    indices: tuple[int, ...],
    retry: OCRCandidate,
    core: str,
    reason: str,
) -> bool:
    if retry.mean_confidence < 80:
        return False
    original_confidence = sum(words[index].confidence for index in indices) / len(
        indices
    )
    original_text = " ".join(words[index].text for index in indices)
    if reason == "protected_term":
        return core.upper() in PROTECTED_LATIN_TERMS
    if reason == "mixed_script":
        return retry.mean_confidence >= original_confidence
    if reason == "placeholder":
        return retry.mean_confidence >= original_confidence - 5
    return (
        reason == "organization"
        and (
            "?" in original_text
            or (
                original_confidence < settings.ocr_high_confidence
                and retry.mean_confidence >= original_confidence + 5
            )
        )
    )


def _single_latin_core(text: str) -> str | None:
    matches = re.findall(r"[A-Za-z][A-Za-z0-9._&/-]*", text)
    return matches[0] if len(matches) == 1 and len(matches[0]) >= 2 else None


def _letters_only(text: str) -> str:
    return "".join(character for character in text if character.isalpha())


def _preserve_outer_punctuation(
    words: list[OCRWord],
    indices: tuple[int, ...],
    core: str,
) -> str:
    original = " ".join(words[index].text for index in indices)
    prefix_match = re.match(r"^[^A-Za-zА-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІі]*", original)
    suffix_match = re.search(r"[^A-Za-zА-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІі]*$", original)
    prefix = prefix_match.group(0) if prefix_match else ""
    suffix = suffix_match.group(0) if suffix_match else ""
    return f"{prefix}{core}{suffix}"


def _replacement_word(
    words: list[OCRWord],
    indices: tuple[int, ...],
    text: str,
    confidence: float,
) -> OCRWord:
    first = words[indices[0]]
    left = min(words[index].left for index in indices)
    top = min(words[index].top for index in indices)
    right = max(words[index].left + words[index].width for index in indices)
    bottom = max(words[index].top + words[index].height for index in indices)
    return OCRWord(
        text=text,
        confidence=confidence,
        left=left,
        top=top,
        width=right - left,
        height=bottom - top,
        block=first.block,
        paragraph=first.paragraph,
        line=first.line,
    )


def _candidate_from_words(
    words: list[OCRWord],
    preprocessing: str,
) -> OCRCandidate:
    if words:
        weighted_total = sum(
            word.confidence * max(len(word.text), 1) for word in words
        )
        total_weight = sum(max(len(word.text), 1) for word in words)
        mean_confidence = weighted_total / total_weight
        low_confidence_ratio = (
            sum(
                word.confidence < settings.ocr_low_word_confidence
                for word in words
            )
            / len(words)
        )
    else:
        mean_confidence = 0.0
        low_confidence_ratio = 1.0
    return OCRCandidate(
        text=_words_to_text(words),
        words=tuple(words),
        mean_confidence=mean_confidence,
        low_confidence_ratio=low_confidence_ratio,
        preprocessing=preprocessing,
    )


def _words_to_text(words: list[OCRWord] | tuple[OCRWord, ...]) -> str:
    lines: dict[tuple[int, int, int], list[OCRWord]] = defaultdict(list)
    for word in words:
        lines[(word.block, word.paragraph, word.line)].append(word)
    ordered_lines = sorted(
        lines.values(),
        key=lambda line_words: (
            min(word.top for word in line_words),
            min(word.left for word in line_words),
        ),
    )
    return "\n".join(
        " ".join(word.text for word in sorted(line_words, key=lambda item: item.left))
        for line_words in ordered_lines
    )


def _candidate_needs_retry(candidate: OCRCandidate) -> bool:
    return bool(_candidate_retry_reasons(candidate))


def _candidate_retry_reasons(candidate: OCRCandidate) -> list[str]:
    reasons = []
    if candidate.mean_confidence < settings.ocr_high_confidence:
        reasons.append("mean_confidence_below_high_threshold")
    if candidate.low_confidence_ratio > 0.10:
        reasons.append("low_confidence_word_ratio_above_retry_threshold")
    if not has_enough_text_signal(candidate.text):
        reasons.append("insufficient_text_signal")
    return reasons


def _candidate_similarity(first: OCRCandidate, second: OCRCandidate) -> float:
    normalize = lambda value: re.sub(r"\s+", " ", value).strip().lower()
    return SequenceMatcher(
        None,
        normalize(first.text),
        normalize(second.text),
        autojunk=False,
    ).ratio()


def _group_projection_positions(values, threshold: float) -> list[int]:
    positions = [index for index, value in enumerate(values) if value >= threshold]
    if not positions:
        return []
    groups: list[list[int]] = [[positions[0]]]
    for position in positions[1:]:
        if position <= groups[-1][-1] + 2:
            groups[-1].append(position)
        else:
            groups.append([position])
    return [round(sum(group) / len(group)) for group in groups]


def _detect_tables(image) -> list[DetectedTable]:
    cv2, numpy = _cv2_and_numpy()
    binary = cv2.adaptiveThreshold(
        image,
        255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        15,
    )
    horizontal_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(image.shape[1] // 35, 20), 1)
    )
    vertical_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (1, max(image.shape[0] // 45, 20))
    )
    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel)
    vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel)
    grid = cv2.bitwise_or(horizontal, vertical)
    contours, _ = cv2.findContours(grid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    tables: list[DetectedTable] = []
    page_area = image.shape[0] * image.shape[1]
    for contour in contours:
        left, top, width, height = cv2.boundingRect(contour)
        if width * height < page_area * 0.02 or width < image.shape[1] * 0.25:
            continue
        local_horizontal = horizontal[top : top + height, left : left + width]
        local_vertical = vertical[top : top + height, left : left + width]
        row_lines = _group_projection_positions(
            numpy.count_nonzero(local_horizontal, axis=1),
            width * 0.35,
        )
        column_lines = _group_projection_positions(
            numpy.count_nonzero(local_vertical, axis=0),
            height * 0.35,
        )
        if len(row_lines) < 2 or len(column_lines) < 2:
            continue
        cells: list[DetectedCell] = []
        invalid_geometry = False
        for row_index in range(len(row_lines) - 1):
            row_top = row_lines[row_index]
            row_bottom = row_lines[row_index + 1]
            if row_bottom - row_top < 12:
                invalid_geometry = True
                continue
            column_index = 0
            while column_index < len(column_lines) - 1:
                span = 1
                while column_index + span < len(column_lines) - 1:
                    boundary = column_lines[column_index + span]
                    line_pixels = numpy.count_nonzero(
                        local_vertical[row_top:row_bottom, max(boundary - 2, 0) : boundary + 3]
                    )
                    if line_pixels >= (row_bottom - row_top) * 0.35:
                        break
                    span += 1
                cell_right_index = column_index + span
                if (
                    column_lines[cell_right_index] - column_lines[column_index]
                    < 12
                ):
                    invalid_geometry = True
                    column_index = cell_right_index
                    continue
                cells.append(
                    DetectedCell(
                        row=row_index,
                        column=column_index,
                        left=left + column_lines[column_index],
                        top=top + row_top,
                        right=left + column_lines[cell_right_index],
                        bottom=top + row_bottom,
                        column_span=span,
                    )
                )
                column_index = cell_right_index
        tables.append(
            DetectedTable(
                left=left,
                top=top,
                right=left + width,
                bottom=top + height,
                rows=len(row_lines) - 1,
                columns=len(column_lines) - 1,
                cells=cells,
                ambiguous=invalid_geometry or not cells,
            )
        )
    return sorted(tables, key=lambda table: (table.top, table.left))


def _point_in_box(
    point: tuple[float, float],
    box: tuple[int, int, int, int],
) -> bool:
    x, y = point
    left, top, right, bottom = box
    return left <= x <= right and top <= y <= bottom


def _assign_words_to_tables(
    tables: list[DetectedTable],
    words: tuple[OCRWord, ...],
) -> None:
    for word in words:
        for table in tables:
            if not _point_in_box(word.center, table.box):
                continue
            matching_cells = [
                cell for cell in table.cells if _point_in_box(word.center, cell.box)
            ]
            if len(matching_cells) == 1:
                matching_cells[0].words.append(word)
            else:
                table.ambiguous = True
            break


def _recover_uncertain_cells(
    tables: list[DetectedTable],
    image,
) -> int:
    retries = 0
    for table in tables:
        for cell_index, cell in enumerate(table.cells):
            if retries >= MAX_CELL_RETRIES:
                cell.uncertain = True
                for remaining in table.cells[cell_index + 1 :]:
                    remaining.uncertain = True
                return retries
            current_confidence = (
                sum(word.confidence for word in cell.words) / len(cell.words)
                if cell.words
                else 0
            )
            if cell.words and current_confidence >= settings.ocr_low_word_confidence:
                continue
            cell.uncertain = bool(cell.words)
            crop = image[
                max(cell.top + 2, 0) : max(cell.bottom - 2, cell.top + 3),
                max(cell.left + 2, 0) : max(cell.right - 2, cell.left + 3),
            ]
            if crop.size == 0 or not _crop_has_text(crop):
                continue
            candidate = _run_tesseract(crop, "cell", psm=6)
            retries += 1
            if not candidate.words or candidate.mean_confidence <= current_confidence:
                cell.uncertain = True
                continue
            cell.words = [
                OCRWord(
                    text=word.text,
                    confidence=word.confidence,
                    left=word.left + cell.left + 2,
                    top=word.top + cell.top + 2,
                    width=word.width,
                    height=word.height,
                    block=word.block,
                    paragraph=word.paragraph,
                    line=word.line,
                )
                for word in candidate.words
            ]
            cell.uncertain = (
                candidate.mean_confidence < settings.ocr_low_word_confidence
            )
    return retries


def _crop_has_text(crop) -> bool:
    cv2, numpy = _cv2_and_numpy()
    if len(crop.shape) == 3:
        crop = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    foreground = cv2.threshold(
        crop, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )[1]
    ratio = numpy.count_nonzero(foreground) / foreground.size
    return 0.003 <= ratio <= 0.45


def _markdown_table(table: DetectedTable) -> str:
    cells_by_position = {(cell.row, cell.column): cell for cell in table.cells}
    rows: list[list[str]] = []
    for row_index in range(table.rows):
        row: list[str] = []
        for column_index in range(table.columns):
            cell = cells_by_position.get((row_index, column_index))
            text = _words_to_text(cell.words).replace("\n", " ") if cell else ""
            if cell and cell.uncertain:
                text = f"{text} [UNCERTAIN_OCR]".strip()
            row.append(text.replace("|", "\\|").strip())
        rows.append(row)
    if not rows:
        return ""
    header = rows[0]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows[1:])
    return "\n".join(lines)


def _compose_page_text(
    words: tuple[OCRWord, ...],
    tables: list[DetectedTable],
) -> str:
    non_table_words = [
        word
        for word in words
        if not any(_point_in_box(word.center, table.box) for table in tables)
    ]
    blocks: list[tuple[int, int, str]] = []
    lines: dict[tuple[int, int, int], list[OCRWord]] = defaultdict(list)
    for word in non_table_words:
        lines[(word.block, word.paragraph, word.line)].append(word)
    for line_words in lines.values():
        ordered = sorted(line_words, key=lambda word: word.left)
        blocks.append(
            (
                min(word.top for word in ordered),
                min(word.left for word in ordered),
                " ".join(word.text for word in ordered),
            )
        )
    for table in tables:
        blocks.append((table.top, table.left, _markdown_table(table)))
    return "\n".join(
        text for _, _, text in sorted(blocks) if text.strip()
    )


def assess_extraction_quality(
    pages: list[ExtractedPage],
) -> ExtractionQualityAssessment:
    page_assessments = [_assess_page_quality(page) for page in pages]
    ocr_pages = [
        page["page_number"]
        for page in page_assessments
        if page["extraction_method"].startswith("ocr")
    ]
    low_quality_pages = [
        page["page_number"]
        for page in page_assessments
        if page["quality"] == "low"
    ]

    if low_quality_pages:
        quality = "low"
    elif ocr_pages:
        quality = "medium"
    else:
        quality = "high"

    reasons = []
    if ocr_pages:
        reasons.append(
            "OCR was used; verify names, dates, identifiers and signature-related "
            "fields against the PDF image."
        )
    if low_quality_pages:
        reasons.append(
            "Low OCR confidence or ambiguous structure was detected; extracted "
            "wording and table associations must not be treated as exact."
        )

    requires_manual_review = bool(ocr_pages or low_quality_pages)
    return ExtractionQualityAssessment(
        quality=quality,
        requires_manual_review=requires_manual_review,
        meta={
            "heuristic": False,
            "confidence_available": any(page.confidence is not None for page in pages),
            "requires_manual_review": requires_manual_review,
            "page_count": len(page_assessments),
            "ocr_page_count": len(ocr_pages),
            "manual_review_pages": ocr_pages,
            "priority_review_pages": low_quality_pages,
            "low_quality_pages": low_quality_pages,
            "reasons": reasons,
            "pages": page_assessments,
        },
    )


def _assess_page_quality(page: ExtractedPage) -> dict:
    text = page.text.strip()
    non_whitespace = [character for character in text if not character.isspace()]
    alphanumeric_count = sum(character.isalnum() for character in non_whitespace)
    suspicious_character_count = sum(
        _is_suspicious_character(character) for character in non_whitespace
    )
    letter_tokens = LETTER_TOKEN_PATTERN.findall(text)
    mixed_script_token_count = sum(
        len(_token_scripts(token)) > 1 for token in letter_tokens
    )
    alphanumeric_ratio = (
        alphanumeric_count / len(non_whitespace) if non_whitespace else 0.0
    )
    mixed_script_ratio = (
        mixed_script_token_count / len(letter_tokens) if letter_tokens else 0.0
    )
    suspicious_character_ratio = (
        suspicious_character_count / len(non_whitespace) if non_whitespace else 0.0
    )

    reasons: list[str] = []
    quality = page.extraction_quality
    if quality == "unknown":
        quality = "medium" if page.extraction_method.startswith("ocr") else "high"
    if not has_enough_text_signal(text):
        quality = "low"
        reasons.append("No reliable text signal was found on this page.")
    if alphanumeric_ratio < 0.55 and len(non_whitespace) >= 30:
        quality = "low"
        reasons.append("The page contains too much non-alphanumeric OCR noise.")
    if suspicious_character_count >= 2 and suspicious_character_ratio >= 0.02:
        quality = "low"
        reasons.append(
            "The page contains suspicious replacement or control characters."
        )
    if mixed_script_token_count >= 2 and mixed_script_ratio >= 0.03:
        quality = "low"
        reasons.append("The page contains many words with mixed writing systems.")
    if page.meta.get("candidate_disagreement"):
        reasons.append("Adaptive OCR candidates disagreed materially.")
    if page.meta.get("ambiguous_table_count"):
        reasons.append("One or more table grids could not be reconstructed reliably.")

    return {
        "page_number": page.page_number,
        "extraction_method": page.extraction_method,
        "quality": quality,
        "confidence": page.confidence,
        "character_count": len(text),
        "alphanumeric_ratio": round(alphanumeric_ratio, 3),
        "mixed_script_token_count": mixed_script_token_count,
        "suspicious_character_count": suspicious_character_count,
        "table_count": page.table_count,
        "uncertain_region_count": page.uncertain_region_count,
        "reasons": reasons,
        **page.meta,
    }


def _token_scripts(token: str) -> set[str]:
    scripts = set()
    for character in token:
        name = unicodedata.name(character, "")
        if "CYRILLIC" in name:
            scripts.add("cyrillic")
        elif "LATIN" in name:
            scripts.add("latin")
    return scripts


def _is_suspicious_character(character: str) -> bool:
    return character in {"\x00", "\ufffd"} or unicodedata.category(character) in {
        "Cc",
        "Cs",
    }


def has_enough_text_signal(text: str) -> bool:
    alphanumeric_count = sum(character.isalnum() for character in text)
    if alphanumeric_count < settings.ocr_min_text_signal_chars:
        return False
    non_whitespace = [character for character in text if not character.isspace()]
    if not non_whitespace:
        return False
    suspicious_count = sum(
        character in {"\x00", "\ufffd"} for character in non_whitespace
    )
    return suspicious_count / len(non_whitespace) < 0.1


def configured_ocr_languages() -> tuple[str, ...]:
    languages = tuple(
        language.strip()
        for language in settings.ocr_languages.replace(",", "+").split("+")
        if language.strip()
    )
    if not languages:
        raise OCRExtractionError("OCR failed: no OCR languages are configured")
    return languages


def format_ocr_error(error: Exception) -> str:
    message = str(error).strip()
    lower_message = message.lower()
    if (
        "traineddata" in lower_message
        or "failed loading language" in lower_message
        or "error opening data file" in lower_message
    ):
        return (
            "OCR failed: configured language data is missing "
            f"({settings.ocr_languages})"
        )
    if "tesseract" in lower_message and (
        "not found" in lower_message or "not installed" in lower_message
    ):
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
