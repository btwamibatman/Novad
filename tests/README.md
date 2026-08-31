# Test suite

Tests are grouped by the part of the application they exercise:

- `api/` — HTTP routes, authentication, document workflows, and tool endpoints.
- `ai/` — AI providers, prompts, document analysis, reviews, and background jobs.
- `documents/` — OCR, extraction quality, artifacts, redaction, and document vision.
- `privacy/` — PII detection, masking, and restoration.
- `security/` — cross-cutting security and ownership checks.
- `core/` — configuration rules.
- `helpers/` — reusable test data builders; this directory contains no tests.

Shared pytest fixtures live in `conftest.py`. Keep feature-specific helpers next to
their tests and move a helper into `helpers/` only when several areas reuse it.

Run the complete suite:

```shell
python -m pytest -q
```

Run one area or one scenario:

```shell
python -m pytest tests/documents -q
python -m pytest tests/api/test_documents.py -k upload -q
```
