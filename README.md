# Document Processing API

[README](README.md) | [Technical Documentation](TECHNICAL.md)

A full-stack application for uploading PDF documents, extracting native or OCR text, and using AI to summarize, review, and answer questions about the content.

## Main Features

- Secure user sessions and per-user document access
- PDF validation, local storage, and document management
- Asynchronous text extraction with a database-backed worker
- Adaptive Tesseract OCR for Russian, Kazakh, and English documents
- Language detection, text metrics, chunking, and extraction-quality checks
- Local Qwen document Q&A, evidence-backed analysis and improvement suggestions
- Optional Gemini analysis or second review of verified protected copies
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

2. Start local Ollama using the setup below. Add `GEMINI_API_KEY` to `.env`
   only if external analysis or an additional external review is required.

   Keep `GEMINI_SERVICE_TIER=unpaid` for the conservative default. The primary UI
   then allows external document analysis only through a verified protected copy.

3. Start PostgreSQL, the API, the analysis worker, and the development frontend:

   docker compose up --build -d

4. Apply database migrations and create a user:

   docker compose exec api alembic upgrade head
   docker compose exec api python -m app.create_user admin

5. Open the application:

Web console: `http://localhost:8000`
Swagger UI: `http://localhost:8000/docs`
Health check: `http://localhost:8000/health`

### Development with automatic updates

After the initial build, start everything with `docker compose up -d` and open
`http://localhost:8000`. No separate `npm run dev` terminal is needed.
Docker Compose automatically loads `docker-compose.override.yml` (use a current
Docker Compose v2 with support for `!reset`). Vite serves the interface on port
8000 and proxies API, health, and documentation requests to FastAPI internally.

logs for frontend api 
```powershell
docker compose logs -f frontend api
```

After changing frontend dependencies, run `docker compose restart frontend`.
For worker code changes, run `docker compose restart analysis-worker`.
Changes to `.env` require container recreation; Python dependencies or Dockerfile
changes require an image rebuild, and database schema changes require migrations.


Stop the services with:

docker compose down


## Local AI setup: Ollama and Qwen3.5-4B

This setup uses Windows with Docker Desktop. Ollama runs on the laptop and serves
Qwen over HTTP; the API and analysis worker run in Docker and connect to it.
The model stays on the laptop and does not need to be copied into the Docker image.


### 1. Download Ollama and the model

Download from the [official Ollama Windows page](https://ollama.com/download/windows)
and start the installed application. 

Open a new PowerShell terminal:

ollama --version
ollama pull qwen3.5:4b
ollama pull qwen3-embedding:0.6b
ollama run qwen3.5:4b


Send a short question to test the model, then enter `/bye` to leave the chat.
The model download is approximately 3.4 GB; runtime RAM/VRAM usage is higher and
depends on context size. Run `ollama list` to see downloaded models and `ollama ps`
after a request to see loaded models and CPU/GPU usage.

### 2. Configure the local Ollama server

Ollama runs in the background on port `11434`. Do not start a second `ollama serve`
process while the desktop application is already serving requests.

For an initial laptop configuration, add these **Windows user environment
variables** through "Edit environment variables for your account":

```dotenv
OLLAMA_CONTEXT_LENGTH=16384
OLLAMA_NUM_PARALLEL=1
OLLAMA_NO_CLOUD=1
```

These set an initial context limit, one parallel request, and local-only operation.
Quit Ollama from the system tray and reopen it after changing the variables.
Putting them in the project's `.env` does not configure the Ollama process on Windows.
See the [Ollama configuration FAQ](https://docs.ollama.com/faq) for details.

Check the local server:

```powershell
Invoke-RestMethod http://localhost:11434/api/tags
```

The response should list `qwen3.5:4b`.

### 3. Pass the connection settings to Docker

Ensure the project's `.env` contains these values (also provided in `.env.example`):

```dotenv
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=qwen3.5:4b
OLLAMA_EMBEDDING_MODEL=qwen3-embedding:0.6b
OLLAMA_TIMEOUT_SECONDS=180
OLLAMA_CONTEXT_LENGTH=16384
SEMANTIC_SEARCH_ENABLED=true
```

Both `api` and `analysis-worker` already use `env_file: .env` in Compose, so no
Dockerfile changes, model volumes, or additional port mappings are required.
Docker passes these values into the containers; Python must read them and send
the HTTP request. Docker does not automatically redirect AI calls.

Inside a container, `localhost` refers to that container. Docker Desktop provides
`host.docker.internal` to reach the laptop; see
[Docker Desktop networking](https://docs.docker.com/desktop/features/networking/).
For a Python process running directly on Windows, use `http://localhost:11434` instead.

From the project directory, start or recreate the services to load the settings:

```powershell
docker compose up -d --force-recreate api analysis-worker
```

### 4. Verify a model response from Docker

Run this block in PowerShell from the project directory. It uses the container's
connection settings and sends a real inference request using
[Ollama's chat API](https://docs.ollama.com/api/chat):

```powershell
docker compose exec api python -c "from app.services.ollama_provider import OllamaProvider; print(OllamaProvider().generate_text('Reply with: ready', max_output_tokens=20).text)"
```

### Document workflows

- Chat always runs locally. Choose a question, whole-document text analysis, or
  improvement suggestions. Each conclusion includes source quotes and page numbers
  where available. Suggestions are labeled separately from document facts.
- Questions use BM25 plus local multilingual embeddings with reciprocal-rank fusion.
  If embeddings are unavailable, the answer discloses that only word search was used.
  A bounded in-memory vector cache avoids repeatedly embedding the same chunks;
  it is rebuilt after restart and does not require a database migration.
- Whole-document chat analysis processes all extracted chunks in batches. Large
  documents can take several minutes. Visual layout is assessed in the protected
  document workflow, not inferred from chat text.
- In Tools, a verified protected copy supports three modes: local analysis, local
  analysis plus external review, or external analysis alone. Local is the default.
  External modes require both existing consent checkboxes. Local failure never
  causes an automatic cloud fallback.
- Combined jobs save the local analysis before sending the protected copy and its
  local draft for external review. The two analyses remain separate, including
  disagreements. A cloud failure leaves the saved local result visible.
- Quote matching checks the actual supplied text, preserving word order and
  punctuation except Unicode/whitespace normalization. It is not an entailment
  check: matching evidence does not prove a conclusion. OCR uncertainty and
  unsupported numbers in chat conclusions are marked for review.
- Local protected analysis processes text page by page; layout uses the configured
  page sample. Coverage and result limits are disclosed. Cross-section consistency
  needs separate review; neither model is treated as an authority.

`AI_PROVIDER` selects the provider for the existing quick summary, text review and
original-page layout endpoints. It does not override explicit protected job modes
or route the local chat to the cloud. Existing external files are cleaned up using
the provider stored on their jobs even after the default provider changes.

Keep `OLLAMA_NO_CLOUD=1` in the Ollama server's Windows environment. The application
accepts only localhost / Docker host Ollama URLs, rejects cloud model names, and
disables HTTP proxies and redirects for local inference. No model name is displayed
in the interface. Models remain server-side metadata for debugging and job identity.

API additions: `POST /api/documents/{id}/ask` accepts `mode` (`question`, `analysis`,
`suggestions`) and returns structured `conclusions`, `limitations`, `pages_reviewed`
and `retrieval_method` alongside the existing answer fields. `POST /api/ai/jobs`
accepts `processing_mode` (`local`, `review`, `external`), defaulting to `local`.
Combined results include `external_review` separately from the primary local result.


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
