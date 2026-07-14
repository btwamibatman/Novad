
## How to Run

Recommended Docker start:

docker compose up --build -d

Open in browser:

- Document Console: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

Stop Docker containers:


docker compose down

Stop and remove database volume for a clean demo reset:

docker compose down -v

Use this reset command if Docker logs show `password authentication failed for user "document_api_user"` because it usually means the old PostgreSQL volume was initialized with a different password.


Local start without Docker:

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Stop local server:

```text
Press Ctrl+C in the terminal where uvicorn is running.
```

## Endpoints

| Method | Endpoint | What it does |
| --- | --- | --- |
| GET | `/` | Opens the web Document Console for uploading, analyzing and managing documents. |
| GET | `/docs` | Opens the Swagger UI where all API endpoints can be tested manually. |
| GET | `/health` | Checks that the FastAPI backend is running. |
| GET | `/api/dashboard/summary` | Returns dashboard metrics such as total documents, processed documents, failed documents, storage usage and detected languages. |
| POST | `/api/documents/upload` | Uploads a PDF file and saves its metadata in the database. |
| GET | `/api/documents` | Returns the list of all uploaded documents. |
| GET | `/api/documents/{document_id}` | Returns full metadata and analysis data for one document. |
| POST | `/api/documents/{document_id}/analyze` | Extracts text from the document and calculates language, word count and character count. |
| POST | `/api/documents/{document_id}/summarize` | Generates an AI summary for a document that has already been analyzed. |
| POST | `/api/documents/{document_id}/content-review` | Checks extracted text in quick or thorough mode. |
| POST | `/api/documents/{document_id}/layout-review` | Performs an advisory visual review of selected PDF pages. |
| POST | `/api/documents/{document_id}/ask` | Answers from relevant extracted document chunks. |
| GET | `/api/documents/{document_id}/download` | Downloads the original stored document file. |
| DELETE | `/api/documents/{document_id}` | Deletes the document record from the database and removes the stored file from disk. |

Important: `/summarize` and `/content-review` work only after `/analyze`. `/layout-review` is a separate PDF-image path and does not require text analysis.
