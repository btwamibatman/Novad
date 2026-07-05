from app.services.ai_summary import _build_prompt


def test_ai_summary_prompt_requests_practical_document_review():
    prompt = _build_prompt("Document text")

    assert "3-5 short practical sentences" in prompt
    assert "Key points" in prompt
    assert "Saved in system" in prompt
    assert "Kazakhstan document formatting check" in prompt
    assert "margins, fonts, real signatures and stamps cannot be verified" in prompt
