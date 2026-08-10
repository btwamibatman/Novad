# Document Processing API

[README](README.md) | [Technical Documentation](TECHNICAL.md)

A full-stack application for uploading PDF documents, extracting native or OCR text, and using AI to summarize, review, and answer questions about the content.

## Main Features

- Secure user sessions and per-user document access
- PDF validation, local storage, and document management
- Asynchronous text extraction with a database-backed worker
- Adaptive Tesseract OCR for Russian, Kazakh, and English documents
- Language detection, text metrics, chunking, and extraction-quality checks
- Gemini summaries, content review, document Q&A, and visual layout review
- Local PII masking before text is sent to the AI provider
- Local PDF compression with basic, recommended, and extreme modes
- Local Word-to-PDF conversion and editable PDF-to-Word beta with OCR for scans
- Confirm-before-apply PDF redaction with personal, financial, visual, and service categories
- Vue 3 web interface and Swagger API documentation

## Quick Start with Docker

1. Create the environment file:

   Copy-Item .env.example .env

2. Add `GEMINI_API_KEY` to `.env` if AI features are required.

3. Start PostgreSQL, the API, and the analysis worker:

   docker compose up --build -d

4. Apply database migrations and create a user:

   docker compose exec api alembic upgrade head
   docker compose exec api python -m app.create_user admin

5. Open the application:

Web console: `http://localhost:8000`
Swagger UI: `http://localhost:8000/docs`
Health check: `http://localhost:8000/health`

Stop the services with:

docker compose down

## Local Development

Local development requires Python 3.12, LibreOffice, Ghostscript, and Tesseract with `rus`, `kaz`, `eng`, and `osd` language data. The Docker image installs all of them.

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --index-url https://download.pytorch.org/whl/cpu -r requirements-torch-cpu.txt
python -m pip install -r requirements-dev.txt
python -m app.create_user admin
uvicorn app.main:app --reload


Run the analysis worker in a second terminal:

.\.venv\Scripts\Activate.ps1
python -m app.analysis_worker


For frontend development:

cd frontend
npm install
npm run dev

## Tests

pytest
cd frontend
npm test
npm run build


This project is intended for educational and demonstration use. AI and OCR results are advisory and should be manually verified for important documents.
ss