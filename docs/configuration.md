# Configuration and AI processing

[Back to Novad](../README.md)

## Configuration

[.env.example](../.env.example) contains the Compose-oriented configuration; [Settings](../app/core/config.py) defines validation and fallback defaults. The values below refer to the example file, which deliberately differs from some Python defaults.

| Setting | Example configuration and purpose |
| --- | --- |
| `DATABASE_URL`, `POSTGRES_*` | PostgreSQL connection and container initialization. Keep credentials and database name consistent; `db` is the Compose hostname. |
| `STORAGE_DIR` | `storage/uploads`; must be accessible to both API and worker. |
| `ALLOWED_HOSTS`, `ENVIRONMENT` | Local hosts and `development`. Production mode requires explicit public hosts and uses secure session cookies. |
| `MAX_UPLOAD_SIZE_BYTES`, `MAX_REQUEST_SIZE_BYTES` | 50 MiB file limit, 55 MiB request limit; the request limit must allow multipart overhead. |
| `MAX_PDF_PAGES`, `SESSION_STORAGE_QUOTA_BYTES` | 100 pages per PDF and 500 MiB user storage quota. |
| `SESSION_TTL_MINUTES` | 120 minutes; authenticated requests refresh the session. |
| `AI_PROVIDER`, `OLLAMA_BASE_URL` | `ollama` and the Docker host URL. Only local Ollama hostnames are accepted by settings validation. |
| `OLLAMA_MODEL`, `OLLAMA_EMBEDDING_MODEL` | `qwen3.5:4b` and `qwen3-embedding:0.6b`. |
| `SEMANTIC_SEARCH_ENABLED` | `true`; enables embeddings alongside lexical retrieval. |
| `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_SERVICE_TIER` | Optional external AI credentials; example model is `gemini-2.5-flash`, tier is `unpaid`. Declare `paid` only for an API project covered by paid services. |
| `OCR_LANGUAGES`, `PII_NER_LANGUAGES` | `rus+kaz+eng` for Tesseract, `kk,ru,en` for Stanza. |
| `PII_MODEL_DIR` | `/opt/stanza_resources` inside Docker; use a local directory for host development. |

OCR thresholds, rendering limits, AI timeouts, retry policy, and worker polling are also configurable in the example file. Keep real keys and local `.env` files out of version control.

## Protected documents and AI

The protected-copy workflow is a separate path from document chat and quick reviews:

1. Preview locally detected sensitive regions and adjust the selection.
2. Apply redactions. The worker rebuilds every page as an image-only PDF, removing the source text layer and interactive structures from the derivative.
3. Re-scan the derivative with OCR and privacy checks. Residual findings, incomplete checks, or detector failures produce `needs_review`; only `ready_for_ai` artifacts pass the protected AI gate.
4. Choose `local` analysis, `review` (local analysis plus Gemini review), or `external` (Gemini analysis). External modes require both processing consent and acknowledgment of provider data terms.
5. Inspect the results and cleanup status. The default retention choice requests deletion of the provider copy after analysis. A failed external review preserves the saved local result.

Document chat always uses Ollama. `AI_PROVIDER` selects the provider for quick summary, content review, and original-page layout review; it does not change chat routing or explicit protected-job modes. There is no automatic cloud fallback after local inference fails. Original-page layout review has a separate image-consent requirement.

> [!NOTE]
> Verification checks the configured detectors and PDF structure; it does not guarantee that every sensitive detail was removed. Quote matching confirms that cited text occurs in the supplied context, not that the conclusion is correct. Review OCR, redactions, and AI output before relying on them. Layout analysis samples pages according to configuration.
