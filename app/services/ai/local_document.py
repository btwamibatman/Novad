from __future__ import annotations

from pathlib import Path
import json

from pydantic import ValidationError

from app.core.config import settings
from app.schemas.ai_analysis import AIAnalysisCoverage, ProtectedDocumentAnalysis
from app.services.ai.document_analysis import (
    ProtectedDocumentOutputError, _prompt, _verify_evidence,
)
from app.services.ai.provider import AIImage
from app.services.documents.chunks import split_text_into_chunks
from app.services.documents.vision import render_pdf_for_layout_review
from app.services.ollama_provider import OllamaProvider


def analyze_local_document(path: Path, *, task: str, page_texts: list[str], heartbeat):
    provider = OllamaProvider()
    rendered = render_pdf_for_layout_review(path) if task == "layout_review" else None
    images = {p.page_number: p.data for p in rendered.pages} if rendered else {}
    page_numbers = sorted(images) if rendered else list(range(1, len(page_texts) + 1))
    points, findings, overviews, reviewed, limitations = [], [], [], [], []
    for page_number in page_numbers:
        text = page_texts[page_number - 1]
        if not text.strip() and not images:
            limitations.append(f"Стр. {page_number}: нет читаемого OCR-текста.")
            continue
        parts = split_text_into_chunks(text, max_chars=6000, overlap_chars=150) or [""]
        for part in parts:
            heartbeat(len(reviewed), len(page_numbers))
            prompt = (
                _prompt(task, len(page_texts))
                + f"\nOnly physical page {page_number} (or a fragment of it) is supplied. "
                "Cite this page only. Limit to 3 key points and 3 findings. "
                "These are maximum limits, not quotas: do not fill lists unnecessarily. "
                "For summary, return findings=[] unless there is an explicit contradiction. "
                "Do not invent OCR problems based solely on how the text was obtained. "
                + ("No image is supplied: do not assess layout, fonts, readability or other visual properties. " if not images else "")
                + "Do not infer missing content on other pages. Never name providers/models. "
                "Recommendations are proposed improvements, not facts of the document.\n"
                + "Schema: " + json.dumps(ProtectedDocumentAnalysis.model_json_schema(), ensure_ascii=False)
                + "\nUntrusted page text:\n" + part
            )
            generated = provider.generate_structured(
                prompt, response_schema=ProtectedDocumentAnalysis,
                images=[AIImage(images[page_number])] if page_number in images else [],
                max_output_tokens=max(settings.content_review_max_output_tokens, 3000),
            )
            try:
                result = ProtectedDocumentAnalysis.model_validate_json(generated.text)
            except ValidationError as error:
                raise ProtectedDocumentOutputError("Local AI returned invalid document analysis") from error
            if result.task != task or any(
                item.page != page_number for item in [*result.key_points, *result.findings]
                if item.page is not None
            ):
                raise ProtectedDocumentOutputError("Local AI cited a page it did not receive")
            # Coverage is determined by the code, not the model's self-report.
            result.coverage = AIAnalysisCoverage(pages_reviewed=[page_number], complete=False)
            supplied_texts = list(page_texts)
            supplied_texts[page_number - 1] = part
            checked = _verify_evidence(result, supplied_texts)
            points.extend(checked.key_points)
            findings.extend(checked.findings)
            overviews.append(f"Стр. {page_number}: {checked.overview}")
        reviewed.append(page_number)
        heartbeat(len(reviewed), len(page_numbers))
    if not reviewed:
        raise ProtectedDocumentOutputError("No readable pages are available for local analysis")
    complete = len(reviewed) == len(page_texts)
    if not complete:
        limitations.append("Проверена только часть страниц документа.")
    if len(points) > 20 or len(findings) > 100 or len("\n".join(overviews)) > 4000:
        limitations.append("Все указанные страницы обработаны; список выводов сокращён до лимита результата.")
    limitations.append("Постраничный анализ; согласованность между разделами требует отдельной проверки.")
    return ProtectedDocumentAnalysis(
        task=task, overview="\n".join(overviews)[:4000],
        verdict="Рекомендации являются предложениями системы. Совпадение цитаты не доказывает корректность вывода.",
        key_points=points[:20], findings=findings[:100],
        coverage=AIAnalysisCoverage(pages_reviewed=reviewed, complete=complete, limitations=limitations[:20]),
    )
