from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

from app.core.config import settings


class DocumentVisionError(RuntimeError):
    pass


@dataclass(frozen=True)
class RenderedPage:
    page_number: int
    data: bytes
    width_mm: float
    height_mm: float


@dataclass(frozen=True)
class RenderedDocument:
    total_pages: int
    pages: list[RenderedPage]
    dpi: int


def pixel_dimensions(width_points: float, height_points: float, dpi: int) -> tuple[int, int]:
    return (
        math.ceil(width_points * dpi / 72),
        math.ceil(height_points * dpi / 72),
    )


def select_render_dpi(
    page_sizes: list[tuple[int, float, float]],
    *,
    requested_dpi: int,
    minimum_dpi: int,
    max_pixels_per_page: int,
) -> int:
    if requested_dpi <= 0:
        raise DocumentVisionError("LAYOUT_REVIEW_DPI must be positive")
    if minimum_dpi <= 0 or minimum_dpi > requested_dpi:
        raise DocumentVisionError(
            "LAYOUT_REVIEW_MIN_DPI must be positive and not exceed LAYOUT_REVIEW_DPI"
        )
    if max_pixels_per_page <= 0:
        raise DocumentVisionError("LAYOUT_REVIEW_MAX_PIXELS_PER_PAGE must be positive")

    effective_dpi = requested_dpi
    for page_number, width_points, height_points in page_sizes:
        width_pixels, height_pixels = pixel_dimensions(
            width_points,
            height_points,
            requested_dpi,
        )
        if width_pixels * height_pixels <= max_pixels_per_page:
            continue

        page_dpi = math.floor(
            72 * math.sqrt(max_pixels_per_page / (width_points * height_points))
        )
        while page_dpi >= minimum_dpi:
            width_pixels, height_pixels = pixel_dimensions(
                width_points,
                height_points,
                page_dpi,
            )
            if width_pixels * height_pixels <= max_pixels_per_page:
                break
            page_dpi -= 1

        if page_dpi < minimum_dpi:
            raise DocumentVisionError(
                f"Page {page_number} exceeds the layout review pixel limit even at minimum DPI"
            )
        effective_dpi = min(effective_dpi, page_dpi)

    return effective_dpi


def select_pages_for_layout_review(
    total_pages: int,
    max_pages: int | None = None,
) -> list[int]:
    if total_pages <= 0:
        return []

    page_limit = settings.layout_review_max_pages if max_pages is None else max_pages
    if page_limit <= 0:
        raise DocumentVisionError("LAYOUT_REVIEW_MAX_PAGES must be positive")
    if total_pages <= page_limit:
        return list(range(1, total_pages + 1))
    if page_limit == 1:
        return [1]

    return sorted(
        {
            round(index * (total_pages - 1) / (page_limit - 1)) + 1
            for index in range(page_limit)
        }
    )


def render_pdf_for_layout_review(path: Path) -> RenderedDocument:
    try:
        import pymupdf
    except ImportError as error:
        raise DocumentVisionError("PyMuPDF is not installed") from error

    try:
        with pymupdf.open(path) as pdf:
            if pdf.needs_pass:
                raise DocumentVisionError(
                    "PDF layout review failed: password-protected PDFs are not supported"
                )
            total_pages = pdf.page_count
            selected_pages = select_pages_for_layout_review(total_pages)
            if not selected_pages:
                raise DocumentVisionError("PDF layout review failed: document has no pages")

            source_pages = [
                (page_number, pdf.load_page(page_number - 1))
                for page_number in selected_pages
            ]
            dpi = select_render_dpi(
                [
                    (page_number, page.rect.width, page.rect.height)
                    for page_number, page in source_pages
                ],
                requested_dpi=settings.layout_review_dpi,
                minimum_dpi=settings.layout_review_min_dpi,
                max_pixels_per_page=settings.layout_review_max_pixels_per_page,
            )

            rendered_pages: list[RenderedPage] = []
            total_inline_bytes = 0
            for page_number, page in source_pages:
                width_pixels, height_pixels = pixel_dimensions(
                    page.rect.width,
                    page.rect.height,
                    dpi,
                )
                pixel_count = width_pixels * height_pixels
                if pixel_count > settings.layout_review_max_pixels_per_page:
                    raise DocumentVisionError(
                        f"Page {page_number} exceeds the layout review pixel limit"
                    )

                pixmap = page.get_pixmap(
                    dpi=dpi,
                    colorspace=pymupdf.csRGB,
                    alpha=False,
                    annots=True,
                )
                image = pixmap.tobytes("png")
                total_inline_bytes += len(image)
                if total_inline_bytes > settings.layout_review_max_inline_bytes:
                    raise DocumentVisionError(
                        "Rendered pages exceed the layout review payload limit"
                    )

                rendered_pages.append(
                    RenderedPage(
                        page_number=page_number,
                        data=image,
                        width_mm=round(page.rect.width * 25.4 / 72, 1),
                        height_mm=round(page.rect.height * 25.4 / 72, 1),
                    )
                )
    except DocumentVisionError:
        raise
    except Exception as error:
        raise DocumentVisionError(
            "PDF layout review failed: document is invalid or corrupted"
        ) from error

    return RenderedDocument(
        total_pages=total_pages,
        pages=rendered_pages,
        dpi=dpi,
    )
