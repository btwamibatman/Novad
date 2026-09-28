# Test suite

Tests are grouped by the part of the application they exercise:

- `api/` — HTTP routes, authentication, document workflows, and tool endpoints.
- `ai/` — AI providers, prompts, document analysis, reviews, and background jobs.
- `documents/` — OCR, extraction quality, artifacts, redaction, and document vision.
- `privacy/` — PII detection, masking, and restoration.
- `security/` — cross-cutting security and ownership checks.
- `core/` — configuration rules.
- `helpers/` — reusable test data builders; this directory contains no tests.

Shared pytest fixtures live in `conftest.py`. Keep feature-specific helpers next to
their tests and move a helper into `helpers/` only when several areas reuse it.

Run the complete suite:

```shell
python -m pytest -q
```

Run one area or one scenario:

```shell
python -m pytest tests/documents -q
python -m pytest tests/api/test_documents.py -k upload -q
```

## Setup

Use Python 3.12, matching the Docker runtime, in a virtual environment. Install
the CPU build of PyTorch before the development requirements:

```shell
python -m pip install --index-url https://download.pytorch.org/whl/cpu -r requirements-torch-cpu.txt
python -m pip install -r requirements-dev.txt
python -m pip check
```

For Linux, install Tesseract and the language packs used by the application:

```shell
sudo apt-get update
sudo apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-rus tesseract-ocr-kaz tesseract-ocr-osd
```

The suite does not require PostgreSQL, a running Ollama server, a Gemini key,
or downloaded Stanza models. API tests use an in-memory SQLite database and
temporary upload directories. The shared fixture resets application settings to
defaults for each test and restores them afterwards. Application modules are
still imported normally: an existing `.env` must pass startup validation.

## Continuous integration

[CI](../.github/workflows/ci.yml) runs on pushes, pull requests and manual
dispatches. It uses Python 3.12 and Node.js 24 on Ubuntu 24.04:

- Backend: install runtime/ML/test dependencies, `pip check`, then the complete
  pytest suite with strict configuration/marker validation.
- Frontend: `npm ci`, all Vitest tests, TypeScript checks and the production
  build, then all Playwright tests in Chromium. See the
  [frontend instructions](../frontend/README.md#checks).

JUnit results, the Playwright HTML report, screenshots and failure traces are
uploaded as GitHub Actions artifacts with a seven-day retention period.
Playwright uses two workers, forbids `test.only`, does not reuse an existing
development server in CI, and does not retry failures automatically.

## Test audit and coverage boundaries

The suite contains meaningful regression checks for ownership, upload limits,
authentication, job retries/cancellation, AI consent and evidence validation,
PDF redaction, client errors, polling and accessible UI interactions. No skipped,
expected-failure or focused-only tests were found during the audit.

Repairs made while enabling CI:

- Updated outdated E2E button names and the redaction-error translation import;
  handled the external-analysis consent dialogs and disambiguated a chat locator.
- Included E2E files in strict TypeScript checking so invalid translation keys
  and fixture types fail the build.
- Restored mutable backend settings and dependency overrides after tests, closed
  HTTP clients, and stopped deleting paths obtained from mutable settings.
- Enabled automatic Vue component unmounting after each test. Browser screenshots
  now use per-test output directories instead of creating untracked project files.
- Strengthened the PDF-to-Word test to open the DOCX and check its editable text;
  a ZIP signature alone did not prove that conversion worked.

Passing these tests does **not** establish the following:

- PostgreSQL compatibility, migration correctness or concurrent worker locking:
  tests create tables from SQLAlchemy metadata in SQLite; they do not run Alembic.
- Application startup/shutdown or the periodic session-cleanup task: the shared
  API clients deliberately do not enter the application lifespan, which would
  initialize the configured application database.
- Full browser-to-backend integration: Playwright serves the real Vue application
  through Vite but intercepts API requests with fixtures. Production assets are
  built separately, not served by these browser tests.
- Real AI response quality, provider connectivity, multilingual NER accuracy or
  broad OCR quality: providers and several OCR/NER paths use fakes. Some local
  PDF rendering, detection and conversion code is exercised directly, but there
  is no representative quality-evaluation dataset or live-model test job.
- Every system conversion dependency: the suite does not validate a real
  LibreOffice Word-to-PDF or Ghostscript compression deployment.

The next useful integration check is a PostgreSQL job that applies migrations
and exercises worker job claiming; live-model quality evaluation should be a
separate, explicitly configured suite.
