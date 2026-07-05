# Document Processing API

Document Processing API is a FastAPI backend for uploading documents, storing metadata in PostgreSQL, extracting text from TXT/PDF files, generating AI summaries, and exposing basic text analysis metrics.

The project is designed for industrial practice reporting and uses only demo/local data.

## Tech Stack

- Python 3.11 or 3.12
- FastAPI
- SQLAlchemy 2.x
- Pydantic v2
- PostgreSQL
- Docker and Docker Compose
- pytest
- pypdf and langdetect
- Google Gemini API for AI summaries
- Uvicorn

## Features

- Health check endpoint
- PDF/TXT document upload
- Local file storage with PostgreSQL metadata
- Document list/detail/download/delete endpoints
- Text extraction from TXT files and PDF text layers
- Language detection, word count and character count
- AI summary generation after text analysis
- Dashboard summary endpoint
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

## Seed Data

Create one processed sample text document:

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
| POST | `/api/documents/upload` | Upload PDF/TXT document |
| GET | `/api/documents` | List documents |
| GET | `/api/documents/{document_id}` | Get one document |
| POST | `/api/documents/{document_id}/analyze` | Extract text and compute metrics |
| POST | `/api/documents/{document_id}/summarize` | Generate AI summary for a processed document |
| GET | `/api/documents/{document_id}/download` | Download stored file |
| DELETE | `/api/documents/{document_id}` | Delete metadata and stored file |

## Data Model

### Document

- `filename`: original uploaded filename
- `stored_path`: stored file identifier resolved through `STORAGE_DIR`
- `content_type`: `text/plain` or `application/pdf`
- `size_bytes`: uploaded file size
- `status`: `uploaded`, `processed` or `failed`
- `extracted_text`: text extracted during analysis
- `detected_language`: language detected from extracted text
- `word_count` and `char_count`: text metrics
- `error_message`: analysis error details for failed documents
- `ai_summary`: generated document summary
- `ai_model`: AI model used for summary generation
- `ai_error`: AI summary error details when generation fails

Files are stored in `storage/uploads`. PostgreSQL stores metadata and analysis results only.

## AI Summary Configuration

`POST /api/documents/{document_id}/summarize` requires a processed document. If the document was not analyzed first, the API returns `400` with `Document must be analyzed first`.

Set `GEMINI_API_KEY` in `.env` to enable real Gemini summary generation. Keep the key local and do not commit it.

## Limitations

This v1 reads TXT files and PDF files with an existing text layer. Image-only PDFs require OCR and are intentionally left as a future improvement.
