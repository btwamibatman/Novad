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
- Local Presidio privacy detection with Kazakh IIN/BIN/IBAN, cards, RU/KK/EN NER, OCR, faces, signatures, QR codes, and barcodes
- Verified protected-PDF workflow: confirmed redactions are rebuilt as an image-only PDF, automatically re-scanned, and only `ready_for_ai` artifacts can be uploaded to AI
- Persistent protected-document AI jobs with explicit provider consent, structured page evidence, retries, cancellation, and remote-file cleanup
- Local PDF compression with basic, recommended, and extreme modes
- Local Word-to-PDF conversion and editable PDF-to-Word beta with OCR for scans
- Confirm-before-apply PDF redaction with personal, financial, visual, and service categories
- Vue 3 web interface and Swagger API documentation

## Quick Start with Docker

1. Create the environment file:

   Copy-Item .env.example .env

2. Add `GEMINI_API_KEY` to `.env` if AI features are required.

   Keep `GEMINI_SERVICE_TIER=unpaid` for the conservative default. The primary UI
   then allows external document analysis only through a verified protected copy.

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
python -c "import stanza; [stanza.download(lang, model_dir='.stanza_resources', processors='tokenize,ner', verbose=False) for lang in ('kk', 'ru', 'en')]"
python -m app.create_user admin
uvicorn app.main:app --reload

For local Windows development, set `PII_MODEL_DIR=.stanza_resources` in `.env`.
Docker uses `/opt/stanza_resources` and downloads the same models during the image build.


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

## Protected document flow

1. Open **Tools**, select a PDF and run the confidential-data preview.
2. Review the locally detected areas, add or remove rectangles, and choose black
   redaction or stable pseudonym labels.
3. Apply the selection. The worker removes interactive PDF structures and rebuilds
   every page from rendered pixels, so hidden object data and selectable source text
   are not copied into the derivative.
4. Verification runs automatically on every page using local OCR and the same privacy
   taxonomy. Residual findings, unchecked pages, detector failures, or unsafe PDF
   structures produce `needs_review`; only a clean artifact becomes `ready_for_ai`.
5. After the user confirms the provider and retention policy, AI receives only that
   verified artifact. The default deletes the provider copy after analysis; failed
   cleanup remains visible and can be retried.
