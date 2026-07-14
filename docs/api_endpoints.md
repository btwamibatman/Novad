# API Endpoints

This document lists the available REST endpoints for Document Processing API.

The API stores uploaded PDF files on disk and stores metadata, extracted text, text metrics, AI summaries and review results in the database.

## Public Pages

| Method | Path | Description |
| --- | --- | --- |
| GET | `/` | Open the static Document Console |
| GET | `/docs` | Open Swagger UI |
| GET | `/health` | Check API status |

## Dashboard

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/dashboard/summary` | Get total document count, processed/failed counts, storage usage and detected language distribution |

Example response:

```json
{
  "total_documents": 3,
  "processed_documents": 2,
  "failed_documents": 1,
  "storage_bytes": 48219,
  "detected_languages": {
    "en": 2
  }
}
```

## Documents

| Method | Path | Description | Request body |
| --- | --- | --- | --- |
| POST | `/api/documents/upload` | Upload a PDF document | `multipart/form-data` with `file` |
| GET | `/api/documents` | List documents | None |
| GET | `/api/documents/{document_id}` | Get one document by id | None |
| POST | `/api/documents/{document_id}/analyze` | Extract text and compute language, word count and character count | None |
| POST | `/api/documents/{document_id}/summarize` | Generate AI summary for an already processed document | None |
| POST | `/api/documents/{document_id}/content-review` | Review extracted text | JSON: `{"mode":"quick"}` or `{"mode":"thorough"}` |
| POST | `/api/documents/{document_id}/layout-review` | Visually review selected PDF pages | None |
| POST | `/api/documents/{document_id}/ask` | Ask a question about relevant extracted chunks | JSON question and history |
| GET | `/api/documents/{document_id}/download` | Download the stored file | None |
| DELETE | `/api/documents/{document_id}` | Delete document metadata and stored file | None |

Upload example:

```bash
curl -X POST http://localhost:8000/api/documents/upload \
  -F "file=@sample.pdf"
```

Analyze example:

```bash
curl -X POST http://localhost:8000/api/documents/1/analyze
```

Summarize example:

```bash
curl -X POST http://localhost:8000/api/documents/1/summarize
```

Content and layout review examples:

```bash
curl -X POST http://localhost:8000/api/documents/1/content-review \
  -H "Content-Type: application/json" \
  -d '{"mode":"quick"}'
curl -X POST http://localhost:8000/api/documents/1/layout-review
```

Document response example:

```json
{
  "id": 1,
  "filename": "sample.pdf",
  "content_type": "application/pdf",
  "size_bytes": 73,
  "status": "processed",
  "extracted_text": "This document contains enough English text for language detection.",
  "extraction_quality": "high",
  "extraction_quality_meta": {"heuristic": true, "requires_manual_review": false},
  "detected_language": "en",
  "word_count": 9,
  "char_count": 65,
  "error_message": null,
  "ai_summary": "A short summary of the uploaded document.",
  "ai_model": "gemini-2.5-flash",
  "ai_error": null,
  "content_review": "The document needs two language corrections.",
  "content_review_model": "gemini-2.5-flash",
  "content_review_error": null,
  "content_review_mode": "quick",
  "content_review_meta": {"complete": true, "batch_count": 1},
  "layout_review": "The sampled pages are visually consistent.",
  "layout_review_model": "gemini-2.5-flash",
  "layout_review_error": null,
  "layout_review_meta": {"complete": false, "reviewed_pages": [1, 5, 9]},
  "created_at": "2026-06-29T10:00:00",
  "updated_at": "2026-06-29T10:01:00"
}
```

## Common Responses

Successful upload requests return HTTP 201 and the created document metadata.

Successful analyze and summarize requests return HTTP 200 and the updated document.

Successful delete requests return HTTP 204 with an empty response body.

If a requested document does not exist, the API returns HTTP 404:

```json
{
  "detail": "Document with id 99 was not found"
}
```

If a file is empty, the API returns HTTP 400:

```json
{
  "detail": "Uploaded file is empty"
}
```

If a file type is unsupported, the API returns HTTP 415:

```json
{
  "detail": "Only PDF files are supported"
}
```

If a document is summarized before analysis, the API returns HTTP 400:

```json
{
  "detail": "Document must be analyzed first"
}
```

If Gemini is not configured, summary generation returns HTTP 503:

```json
{
  "detail": "GEMINI_API_KEY is not configured"
}
```

FastAPI returns HTTP 422 with validation details when path parameters or request data are invalid.
