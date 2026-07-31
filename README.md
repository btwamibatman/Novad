# Document Processing API

A full-stack application for uploading PDF documents, extracting native or OCR text, and using AI to summarize, review, and answer questions about the content.

## Main Features

- Secure user sessions and per-user document access
- PDF validation, local storage, and document management
- Asynchronous text extraction with a database-backed worker
- Adaptive Tesseract OCR for Russian, Kazakh, and English documents
- Language detection, text metrics, chunking, and extraction-quality checks
- Gemini summaries, content review, document Q&A, and visual layout review
- Local PII masking before text is sent to the AI provider
- Vue 3 web interface and Swagger API documentation

## Quick Start with Docker

1. Create the environment file:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Add `GEMINI_API_KEY` to `.env` if AI features are required.

3. Start PostgreSQL, the API, and the analysis worker:

   ```bash
   docker compose up --build -d
   ```

4. Apply database migrations and create a user:

   ```bash
   docker compose exec api alembic upgrade head
   docker compose exec api python -m app.create_user admin
   ```

5. Open the application:

   - Web console: `http://localhost:8000`
   - Swagger UI: `http://localhost:8000/docs`
   - Health check: `http://localhost:8000/health`

Stop the services with:

```bash
docker compose down
```

## Local Development

Local development requires Python 3.12 and Tesseract with `rus`, `kaz`, `eng`, and `osd` language data.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m app.create_user admin
uvicorn app.main:app --reload
```

Run the analysis worker in a second terminal:

```powershell
.\.venv\Scripts\Activate.ps1
python -m app.analysis_worker
```

For frontend development:

```bash
cd frontend
npm install
npm run dev
```

## Tests

```bash
pytest
cd frontend
npm test
npm run build
```

## Documentation

- [Technical reference](TECHNICAL.md)
- [Detailed API examples](docs/api_endpoints.md)
- [Database migrations](docs/alembic_migration.md)

This project is intended for educational and demonstration use. AI and OCR results are advisory and should be manually verified for important documents.
