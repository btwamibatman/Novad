Core Architecture Flow
Vue 3 Client → FastAPI → PostgreSQL + Local PDF Storage → Async Worker (Tesseract OCR) → Local PII Masking (Stanza) → Gemini API

Tech Stack
Backend & DB: Python 3.12, FastAPI, PostgreSQL (SQLite local), SQLAlchemy 2, Alembic

Frontend: Vue 3, TypeScript, Pinia, Vite

Document & OCR: PyMuPDF, OpenCV, Tesseract (rus+kaz+eng)

Privacy & AI: Stanza NER + Regex (PII masking), Gemini API (gemini-2.5-flash)

Key Pipeline Steps
Upload Validation: Enforces PDF only, max 10 MiB, max 100 pages, max 30 MiB user quota.

Analysis Enqueue: POST /analyze returns 202 Accepted. Database row locking prevents duplicate worker execution.

Extraction & OCR: Reads native text first. Falls back to OpenCV preprocessing + Tesseract OCR for scanned/low-confidence pages.

Chunking & PII Masking: Splits text into overlapping chunks. Pseudonymizes sensitive data locally before sending context to Gemini. Restores placeholders on response.

Essential API Endpoints
Auth
POST /api/auth/login – Create session (HttpOnly cookie)

GET /api/auth/me – Current user info

Documents & Analysis
POST /api/documents/upload – Upload PDF (201)

POST /api/documents/{id}/analyze – Start async worker job (202)

GET /api/documents/{id} – Poll status until processed or failed

POST /api/documents/{id}/summarize – Generate summary (requires processed)

POST /api/documents/{id}/ask – Chunk-based Q&A (requires processed)

POST /api/documents/{id}/layout-review – Visual review (requires explicit image consent)

Critical Rules & Limits
Security: Argon2 password hashing, HttpOnly / SameSite=Lax session cookies, strict per-user document isolation.

Fail-Closed PII: If NER models fail or placeholders do not match during unmasking, the request aborts.

Concurrency: Analysis queue uses PostgreSQL row locks; rate limiting is currently process-local.