# Setup and development

[Back to Novad](../README.md)

## Quick start

The primary setup uses **Docker Desktop**, **Docker Compose v2 with `!reset` support**, and **Ollama running on the host**. Commands below use PowerShell. Git is required to clone the repository; Python and Node.js run inside the containers.

### 1. Clone and configure

```powershell
git clone https://github.com/btwamibatman/Novad.git
cd Novad
Copy-Item .env.example .env
```

Review `.env` before starting. Its checked-in database values are development examples; choose your own database password and update `DATABASE_URL` to match. Keep `AI_PROVIDER=ollama`. A Gemini key is not needed for local processing.

### 2. Prepare local AI

With Ollama installed and running on the host:

```powershell
ollama pull qwen3.5:4b
ollama pull qwen3-embedding:0.6b
Invoke-RestMethod http://localhost:11434/api/tags
```

The model names match [.env.example](../.env.example). The containers connect through `OLLAMA_BASE_URL=http://host.docker.internal:11434`; a Python process running directly on the host uses `http://localhost:11434`.

For the existing Windows setup, configure `OLLAMA_NO_CLOUD=1`, `OLLAMA_CONTEXT_LENGTH=16384`, and `OLLAMA_NUM_PARALLEL=1` in the **host Ollama process environment**, then restart Ollama. The project's `.env` configures the application and containers, not the separately running Ollama server. Uploads, OCR, and PDF tools can run without Ollama; AI actions require it.

### 3. Build and initialize

Start the database and build the application image:

```powershell
docker compose up -d db
docker compose build api
```

The first build installs document-processing binaries, CPU PyTorch, and Stanza models for `kk`, `ru`, and `en`; it requires network access for these downloads.

For a **new, empty database**, initialize the tables before applying migrations:

```powershell
docker compose run --rm api python -c "from app.core.database import init_db; init_db()"
docker compose run --rm api alembic upgrade head
docker compose run --rm api python -m app.create_user admin
```

The user-creation command prompts for a password and confirmation. `admin` is a username, not a separate administrator role. The initial migration assumes the original `documents` table exists, which is why table initialization comes first. For an existing database, back it up and apply migrations with the API and worker stopped; do not repeat the fresh-database initialization step.

Start the complete workspace:

```powershell
docker compose up -d
```

| Open | Address |
| --- | --- |
| Web console | [localhost:8000](http://localhost:8000) |
| Swagger UI | [localhost:8000/docs](http://localhost:8000/docs) |
| OpenAPI schema | [localhost:8000/openapi.json](http://localhost:8000/openapi.json) |
| Health endpoint | [localhost:8000/health](http://localhost:8000/health) |

Sign in with the account you created. `/health` reports API availability; it does not check the database, worker, or AI providers.

### 4. Process a document

1. Upload a PDF in **Documents**. Uploading automatically queues extraction and OCR where needed.
2. Wait for processing to finish, then inspect the text, language metrics, and extraction quality. Keep `analysis-worker` running; otherwise queued work will not advance.
3. Ask a question, request a summary, or review the document. Failed extraction can be retried without uploading the file again.
4. Open **Tools** for compression, conversion, or confidential-data review.

```powershell
docker compose logs -f frontend api analysis-worker
docker compose down
```

Compose stores database data in `postgres_data` and files in `./storage`. Ordinary `docker compose down` preserves these. Do not remove the database volume or storage directory if you need the documents.

## Development

The automatically loaded [Compose override](../docker-compose.override.yml) provides API reload and Vite hot reload. Restart `analysis-worker` after worker code changes and `frontend` after frontend dependency changes. Recreate containers after `.env` changes; rebuild the API image after Python dependency or Dockerfile changes.

<details>
<summary>Run Python and Vite directly on the host</summary>

Use Python 3.12 and Node.js 24, matching Docker and CI. Install Tesseract with `rus`, `kaz`, `eng`, and `osd` data, plus LibreOffice and Ghostscript for the document tools. Make their executables discoverable on the host.

From the repository root, create `.env` from the example if you have not already done so. For local SQLite development, change these entries:

```dotenv
DATABASE_URL=sqlite:///./documents.db
OLLAMA_BASE_URL=http://localhost:11434
PII_MODEL_DIR=.stanza_resources
```

Install dependencies and download the NER models:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --index-url https://download.pytorch.org/whl/cpu -r requirements-torch-cpu.txt
python -m pip install -r requirements-dev.txt
python -m pip check
python -c "import stanza; [stanza.download(lang, model_dir='.stanza_resources', processors='tokenize,ner', verbose=False) for lang in ('kk', 'ru', 'en')]"
```

For a new database, initialize it and create a user before starting the API:

```powershell
python -c "from app.core.database import init_db; init_db()"
alembic upgrade head
python -m app.create_user admin
uvicorn app.main:app --reload
```

In a second terminal, activate the same virtual environment and start the worker:

```powershell
.\.venv\Scripts\Activate.ps1
python -m app.analysis_worker
```

In a third terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173/`. Vite proxies API requests to port `8000`. Alternatively, `npm run build` writes the frontend to `app/web/dist`, allowing FastAPI to serve it at `http://localhost:8000/`.

</details>

<details>
<summary>Run the bundled frontend without development overrides</summary>

After database initialization, user creation, and image build, stop the development services and select only the base Compose file:

```powershell
docker compose down
docker compose -f docker-compose.yml up -d
```

FastAPI now serves the bundled UI on port `8000`; Vite is not started. This is a packaging option, not a documented cloud deployment. No automated deployment workflow is included.

</details>

## Repository guide

```text
app/
  api/              HTTP routes and authentication dependencies
  core/             Settings and database setup
  models/           SQLAlchemy tables
  schemas/          Request and response contracts
  crud/             Document, user, and session persistence
  services/         OCR, privacy, retrieval, AI, and PDF processing
  analysis_worker.py Database-backed processing loop
frontend/           Vue application, Vitest tests, and Playwright scenarios
alembic/            Schema migrations
tests/              Backend regression tests and fixtures
docs/               Technical notes, including older project documentation
.github/workflows/  Continuous integration
```

Start with [application routes](../app/api/router.py), [settings](../app/core/config.py), [frontend development](../frontend/README.md), and the [test guide](../tests/README.md). Some older files under `docs/` describe the previous task-tracker implementation or earlier AI behavior; use this README, the current code, and generated OpenAPI schema for the current application.
