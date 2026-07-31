# Technical Reference

## System Overview

The application separates HTTP handling from CPU-intensive document analysis:

```text
Vue client -> FastAPI API -> PostgreSQL + local PDF storage
                         -> analysis_jobs table -> analysis worker -> OCR pipeline
                         -> local PII masking -> Gemini API
```

`POST /api/documents/{document_id}/analyze` creates or reuses a database job and immediately returns HTTP `202`. The worker claims pending jobs, processes PDF pages, stores progress, and persists the extracted text and quality metadata.

## Tech Stack

| Area | Technologies | Purpose |
| --- | --- | --- |
| Backend | Python 3.12, FastAPI, Uvicorn, Pydantic | REST API, validation, and application server |
| Database | PostgreSQL, SQLAlchemy 2, Alembic | Persistent data, ORM, and schema migrations |
| Local development | SQLite | Database fallback without Docker |
| Frontend | Vue 3, TypeScript, Pinia, Vue I18n, Vite | Browser-based document console |
| PDF processing | pypdf, PyMuPDF | PDF validation, native text extraction, and page rendering |
| OCR | Tesseract, pytesseract, OpenCV, NumPy | Multilingual OCR and image preprocessing |
| Text analysis | langdetect | Per-chunk language detection and text statistics |
| Privacy | Stanza NER and regex recognizers | Local PII detection and pseudonymization |
| AI | Google Gemini through `google-genai` | Summaries, reviews, Q&A, and visual analysis |
| Infrastructure | Docker, Docker Compose | API, worker, and PostgreSQL services |
| Testing | pytest, Vitest, Playwright | Backend, frontend, and end-to-end tests |

## API Endpoints

Swagger UI is available at `/docs`. Except for the public routes and login, API routes use the HttpOnly session cookie returned by `POST /api/auth/login`.

### Public and Authentication

| Method | Path | Purpose | Request |
| --- | --- | --- | --- |
| GET | `/` | Serve the Vue application | None |
| GET | `/health` | Check API availability | None |
| GET | `/docs` | Open Swagger UI | None |
| POST | `/api/auth/login` | Create a server-side session | `{"username":"admin","password":"..."}` |
| GET | `/api/auth/me` | Return the current session and user | None |
| POST | `/api/auth/logout` | Revoke the current session | None |
| GET | `/api/session` | Return the internal session ID and expiry | None |

### Documents and Dashboard

| Method | Path | Purpose | Request / result |
| --- | --- | --- | --- |
| GET | `/api/dashboard/summary` | Return user document and storage metrics | HTTP `200` |
| POST | `/api/documents/upload` | Validate and store a PDF | Multipart `file`; HTTP `201` |
| GET | `/api/documents` | List the current user's documents | HTTP `200` |
| GET | `/api/documents/{document_id}` | Return document data and processing state | HTTP `200` |
| POST | `/api/documents/{document_id}/analyze` | Enqueue idempotent background analysis | HTTP `202` |
| POST | `/api/documents/{document_id}/summarize` | Generate a summary from processed text | HTTP `200` |
| POST | `/api/documents/{document_id}/content-review` | Review content quality | `{"mode":"quick"}` or `{"mode":"thorough"}` |
| POST | `/api/documents/{document_id}/layout-review` | Review selected pages as images | `{"consent_to_external_image_processing":true}` |
| POST | `/api/documents/{document_id}/ask` | Answer from relevant document chunks | `{"question":"...","history":[]}` |
| GET | `/api/documents/{document_id}/download` | Download the original PDF | File response |
| DELETE | `/api/documents/{document_id}` | Delete the database record and stored PDF | HTTP `204` |

`summarize`, `content-review`, and `ask` require document status `processed`. Poll `GET /api/documents/{document_id}` after starting analysis until the status is `processed` or `failed`. Layout review does not require extracted text, but explicit consent is mandatory because page images may be sent to the external AI provider.

## Document Processing Pipeline

1. **Upload validation:** only PDF files are accepted. The API checks the extension, media type, `%PDF-` signature, encryption, page count, request size, file size, and user storage quota.
2. **Background job:** the API records a `pending` job. A separate worker claims it with a database lock and updates page-level progress.
3. **Native extraction:** text is read in page order. Pages with reliable embedded text avoid OCR.
4. **Adaptive OCR:** scanned or weak-text pages are rendered with PyMuPDF and processed locally with OpenCV. The pipeline corrects orientation and skew, improves contrast, and may retry with adaptive thresholding.
5. **Tesseract OCR:** Tesseract returns text and word-level confidence using `rus+kaz+eng` by default. Low-confidence Latin/numeric spans and ruled table cells can be retried separately.
6. **Quality metadata:** the service records extraction method, confidence, table count, uncertain regions, and a `high`, `medium`, or `low` quality rating.
7. **Chunking:** page text is split into overlapping chunks. Language, word count, and character count are stored for later retrieval and AI operations.

Tesseract is used because scanned PDFs contain images rather than a searchable text layer. It runs locally, supports the project's three document languages, and prevents automatic OCR page images from being sent to Gemini.

## AI Features

- **Summary:** summarizes one chunk directly or uses chunk summaries followed by reduction for larger documents.
- **Content review:** `quick` samples representative content; `thorough` reviews consecutive batches and reduces the findings.
- **Document Q&A:** selects up to five relevant chunks with local token matching before sending limited context to Gemini.
- **Layout review:** renders a limited set of pages in memory and sends them to Gemini only after explicit consent. Rendered PNG files are not persisted.

Before text-based AI requests, regex rules and local Stanza NER replace detected PII with stable placeholders. The mapping remains in memory for that request and is restored in the response. Missing NER models or unknown returned placeholders cause the operation to fail closed.

## Persistence Model

| Data | Location |
| --- | --- |
| Users and password hashes | `users` table |
| Hashed session tokens and expiry | `sessions` table |
| File metadata, extracted text, AI results, and status | `documents` table |
| Page-linked text and extraction metadata | `document_chunks` table |
| Background job state and attempts | `analysis_jobs` table |
| Original PDF files | `storage/uploads` |

PostgreSQL is used by Docker Compose. SQLite is the default local fallback. Existing databases should be upgraded with `alembic upgrade head`.

## Security and Operational Controls

- Passwords use the recommended `pwdlib` Argon2 hasher.
- Session tokens are random, stored as SHA-256 hashes, and sent in `HttpOnly`, `SameSite=Lax` cookies.
- Production cookies are `Secure` and use the `__Host-` prefix.
- Document queries are scoped to the authenticated user.
- Trusted hosts, request limits, PDF limits, storage quotas, timeouts, and per-operation rate limits are enforced.
- Uploaded filenames are sanitized; stored files receive UUID names.

Rate limiting is currently process-local, so multiple API replicas would require a shared limiter such as Redis. The analysis queue is database-backed and workers use row locking to avoid claiming the same pending job.

## Main Configuration

The complete configuration is documented in `.env.example`. The most important variables are:

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATABASE_URL` | SQLite locally | SQLAlchemy database connection |
| `GEMINI_API_KEY` | Empty | Enables AI features |
| `GEMINI_MODEL` | `gemini-2.5-flash` | AI model name |
| `MAX_UPLOAD_SIZE_BYTES` | 10 MiB | Maximum PDF size |
| `MAX_PDF_PAGES` | `100` | Maximum pages per upload |
| `SESSION_STORAGE_QUOTA_BYTES` | 30 MiB | Maximum stored PDF bytes per user |
| `OCR_LANGUAGES` | `rus+kaz+eng` | Installed Tesseract languages |
| `OCR_RENDER_DPI` | `300` | Preferred OCR render resolution |
| `LAYOUT_REVIEW_MAX_PAGES` | `3` | Maximum pages sent for visual review |
| `PII_MASKING_ENABLED` | `true` | Enable local PII pseudonymization |

## Known Limitations

- OCR accuracy depends on scan quality and installed Tesseract language data.
- Extraction-quality scores are heuristic; names, dates, identifiers, and tables require manual verification.
- Borderless or ambiguous tables may remain plain OCR text.
- Layout review samples a limited number of pages and does not certify legal compliance or authenticity.
- PII detection reduces exposure but cannot guarantee detection of every sensitive value.
- Gemini calls require network access and send pseudonymized text, or explicitly approved page images, to an external provider.
