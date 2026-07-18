# Document Processing API

Document Processing API is a FastAPI backend for uploading PDF documents, extracting native or OCR text, generating AI summaries, reviewing content quality, and performing an advisory visual layout review.

The project is designed for industrial practice reporting and uses only demo/local data.

## Tech Stack

- Python 3.11 or 3.12
- FastAPI
- SQLAlchemy 2.x
- Pydantic v2
- PostgreSQL
- Docker and Docker Compose
- pytest
- pypdf, OCRmyPDF, Tesseract, PyMuPDF and langdetect
- Google Gemini API through the `google-genai` SDK
- Uvicorn

## Features

- Health check endpoint
- PDF-only document upload
- Local file storage with PostgreSQL metadata
- Document list/detail/download/delete endpoints
- Per-page PDF text extraction with one batch OCR fallback for weak pages
- Persisted extraction-quality gate with manual-review warnings for OCR pages
- Language detection, word count and character count
- AI summary generation after text analysis
- Quick representative or thorough chunked content-quality review
- Ephemeral visual review of selected PDF pages under general RK document rules
- Dashboard summary endpoint
- Username/password authentication with server-side sessions
- Static Document Console at `/`
- Swagger UI at `/docs`
- Basic pytest coverage

## Project Structure

```text
document-processing-api/
├── app/
│   ├── main.py
│   ├── api/
│   ├── core/
│   ├── models/
│   ├── schemas/
│   ├── crud/
│   ├── services/
│   ├── web/
│   └── seed.py
├── tests/
├── storage/uploads/
├── .env.example
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

## Docker Setup

Create your local environment file:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Run the API and PostgreSQL:

```bash
docker compose up --build
```

For an existing database, apply the Alembic migration after rebuilding:

```bash
docker compose exec api alembic upgrade head
```

Create the first user. The password is requested twice without being displayed:

```bash
docker compose exec api python -m app.create_user admin
```

If the database contains documents created before authentication was enabled, assign
them explicitly to that user:

```bash
docker compose exec api python -m app.claim_legacy_documents admin
```

Open:

- Document Console: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

If you previously ran the old workflow tracker version or an earlier document schema without AI summary columns, reset the old Docker volume before starting:

```bash
docker compose down -v
docker compose up --build
```

## Local Setup Without Docker

This mode uses the default SQLite fallback database.

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

For local development, create a user with `python -m app.create_user admin` and sign
in through the same page. Development cookies work over `http://localhost`; production
cookies require HTTPS. Authentication is not bypassed in development. If convenient,
set a longer local-only `SESSION_TTL_MINUTES` in `.env` instead of disabling auth.

Keep `ENVIRONMENT=development` in the local `.env`. On an HTTPS production server,
set `ENVIRONMENT=production`; the session cookie then uses the host-only
`__Host-document_session` name together with `Secure`, `HttpOnly`, `SameSite=Lax`
and `Path=/`. Unsupported environment names fail configuration validation. Do not
enable production mode over local HTTP because browsers will not return a `Secure`
cookie over an unencrypted connection.

Requests are accepted only for hosts listed in `ALLOWED_HOSTS`. The development
default is `localhost,127.0.0.1,testserver`; production requires an explicit public
domain or IP and rejects the unrestricted `*` value. `MAX_REQUEST_SIZE_BYTES` limits
the complete HTTP request body to 11 MiB, including multipart framing, while
`MAX_UPLOAD_SIZE_BYTES` keeps the PDF itself limited to 10 MiB. Oversized requests
return HTTP 413 and partial upload files are removed. When Nginx is added, configure
its request-body limit to match this application boundary.

## Seed Data

Create one processed sample PDF document:

```bash
docker compose exec api python -m app.seed
```

Without Docker:

```bash
python -m app.seed
```

## Run Tests

With Docker:

```bash
docker compose exec -u root api pip install -r requirements-dev.txt
docker compose exec api pytest
```

Without Docker:

```bash
pip install -r requirements-dev.txt
pytest
```

## API Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/health` | API health check |
| GET | `/api/dashboard/summary` | Document metrics summary |
| POST | `/api/documents/upload` | Upload a PDF document |
| GET | `/api/documents` | List documents |
| GET | `/api/documents/{document_id}` | Get one document |
| POST | `/api/documents/{document_id}/analyze` | Extract text and compute metrics |
| POST | `/api/documents/{document_id}/summarize` | Generate AI summary for a processed document |
| POST | `/api/documents/{document_id}/content-review` | Review extracted text in `quick` or `thorough` mode |
| POST | `/api/documents/{document_id}/layout-review` | Review selected PDF pages visually |
| POST | `/api/documents/{document_id}/ask` | Ask a question using relevant extracted chunks |
| GET | `/api/documents/{document_id}/download` | Download stored file |
| DELETE | `/api/documents/{document_id}` | Delete metadata and stored file |

## Data Model

### Document

- `filename`: original uploaded filename
- `stored_path`: stored file identifier resolved through `STORAGE_DIR`
- `content_type`: `application/pdf`
- `size_bytes`: uploaded file size
- `status`: `uploaded`, `processed` or `failed`
- `extracted_text`: text extracted during analysis
- `extraction_quality`, `extraction_quality_meta`: heuristic quality level and manual-review details
- `detected_language`: language detected from extracted text
- `word_count` and `char_count`: text metrics
- `error_message`: analysis error details for failed documents
- `ai_summary`: generated document summary
- `ai_model`: AI model used for summary generation
- `ai_error`: AI summary error details when generation fails
- `content_review`, `content_review_model`, `content_review_error`, `content_review_mode`, `content_review_meta`: content-quality review state
- `layout_review`, `layout_review_model`, `layout_review_error`, `layout_review_meta`: visual review state

Files are stored in `storage/uploads`. PostgreSQL stores metadata and analysis results only.

## AI Summary Configuration

`POST /api/documents/{document_id}/summarize` requires a processed document. If the document was not analyzed first, the API returns `400` with `Document must be analyzed first`.

Set `GEMINI_API_KEY` in `.env` to enable Gemini. `AI_PROVIDER=gemini` is the current provider; the service boundary is intentionally provider-neutral so a local provider can be added in a later phase. `GEMINI_THINKING_BUDGET=0` keeps Gemini 2.5 Flash latency and output-token use predictable for the free tier; raise it deliberately if deeper reasoning is worth the quota. Keep the key local and do not commit it.

`quick` content review makes one representative text request. `thorough` review checks up to six consecutive batches and reduces the findings (at most seven Gemini calls per operation by default); oversized documents are rejected by the synchronous batch limit until background jobs are introduced.

Layout review renders at most `LAYOUT_REVIEW_MAX_PAGES` pages in memory. It starts at `LAYOUT_REVIEW_DPI` and can reduce the effective resolution down to `LAYOUT_REVIEW_MIN_DPI` when unusual PDF page boxes would exceed the per-page pixel guard. PNG files are never persisted and do not count toward session storage quota.

## Privacy and Review Scope

This project is intended for demo/local data. With Gemini, extracted text and rendered page images are sent to an external Google API. Page images may contain signatures, stamps, photographs and other visual personal data. Google currently marks free-tier Gemini content as eligible for product improvement. Do not use a free-tier key for confidential or production documents without an approved data-processing policy and provider terms review.

The visual result is advisory. It uses the general document rules established by [RK Order No. 236](https://adilet.zan.kz/rus/docs/V2300033339) as a baseline, but it does not certify legal compliance and cannot authenticate signatures, stamps, logos or coats of arms. Content review checks internal consistency only; it does not perform external fact-checking or plagiarism detection.

## Limitations

- AI calls are synchronous in this phase. Background jobs are deferred to the local-AI phase.
- OCR quality depends on scan quality and installed `rus+kaz+eng` Tesseract language data. The quality gate is heuristic: every OCR page remains advisory and requires manual verification of names, dates and identifiers.
- Visual review checks selected pages by default, so it cannot prove that an element is absent from unreviewed pages.

..
