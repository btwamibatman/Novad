from app.core.config import settings


class AISummaryError(RuntimeError):
    pass


class AISummaryNotConfigured(AISummaryError):
    pass


def _build_prompt(text: str) -> str:
    return (
        "You are an assistant for a document processing backend.\n"
        "Analyze the extracted document text and answer in the same language as the document.\n"
        "Return only the analysis text. Do not use markdown tables.\n"
        "If the extracted text looks garbled but clearly comes from Cyrillic PDF text, infer the readable meaning and write normal readable text.\n"
        "Always include all four sections below, keeping each section compact:\n"
        "1. Summary: 3-5 short practical sentences about what the document is about.\n"
        "2. Key points: 3-5 bullet points with the most important facts.\n"
        "3. Saved in system: one sentence saying the document was analyzed and the AI summary is saved in the document record after successful generation.\n"
        "4. Kazakhstan document formatting check: 2-4 sentences with a preliminary verdict based only on extracted text. Check for title, student/person details, organization/base, dates/period, structured work items, responsible persons, signature or stamp placeholders. Say compliant, partially compliant, or not enough information. Also state that margins, fonts, real signatures and stamps cannot be verified from extracted text alone.\n\n"
        f"Document text:\n{text}"
    )


def summarize_text(text: str) -> tuple[str, str]:
    cleaned_text = text.strip()
    if not cleaned_text:
        raise AISummaryError("Document text is empty")
    if not settings.gemini_api_key:
        raise AISummaryNotConfigured("GEMINI_API_KEY is not configured")

    import google.generativeai as genai

    model_name = settings.gemini_model
    prompt_text = cleaned_text[: settings.ai_summary_max_chars]

    try:
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(
            _build_prompt(prompt_text),
            generation_config={
                "max_output_tokens": settings.ai_summary_max_output_tokens,
                "temperature": 0.2,
            },
        )
    except Exception as exc:
        raise AISummaryError(f"Gemini API request failed: {exc}") from exc

    try:
        summary = (response.text or "").strip()
    except ValueError as exc:
        # response.text raises ValueError when there are no valid candidates
        # (e.g. blocked by safety filters, finish_reason != STOP)
        raise AISummaryError(f"Gemini returned no usable content: {exc}") from exc

    if not summary:
        raise AISummaryError("AI returned an empty summary")

    return summary, model_name