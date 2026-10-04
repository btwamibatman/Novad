# Docker smoke test

Run from the repository root with Python 3.12, Docker and Compose 2.24.4 or newer:

```shell
python tests/smoke/run.py
python tests/smoke/run.py --skip-build --verify-failures
```

The first command builds the actual Dockerfile, starts PostgreSQL, initializes
tables (required by the legacy first migration), runs `alembic upgrade head`,
then starts API and worker. It waits at most 180 seconds for healthy services,
logs in with a randomly generated disposable account, uploads `sample.pdf`, and
checks that the worker produces the expected text and nonzero text metrics.
Processing has a sixty-second deadline and HTTP requests have five-second
timeouts. The build has a thirty-minute timeout; the CI job has forty minutes.

`sample.pdf` is a 671-byte, single-page PDF with this native text:

> Novad smoke test confirms document processing works.

It contains no personal data. It tests queue processing and text extraction, not
scanned-page OCR quality or AI quality. No Ollama/Gemini service is required.

`--verify-failures` additionally freezes the worker with `SIGSTOP`, waits up to
120 seconds for unhealthy status, and verifies that PDF processing times out.
It restores the process with `SIGCONT`, then tests an exited worker, stops the
database to check `/ready=503` and `/health=200`, and verifies recovery.

The runner uses project `novad-docker-smoke`, image `novad-docker-smoke:local`,
project-scoped volumes and public disposable credentials in `compose.yml`.
The empty `compose.env` prevents loading your `.env`. Your existing application
image, database and storage are not used. API and database ports are not exposed
on the host. Do not run
two copies concurrently on the same Docker daemon because the project name is
fixed. Service environments are overridden explicitly to avoid picking up host
database credentials or AI keys.

On failure, container logs are printed before cleanup. A `finally` block always
attempts `docker compose down -v --remove-orphans`; CI also has an `always()`
cleanup step for interrupted runs. Abrupt host termination or daemon failure
can prevent cleanup; rerun the command below against this test project only:

```shell
docker compose --project-name novad-docker-smoke --env-file tests/smoke/compose.env -f docker-compose.yml -f tests/smoke/compose.yml down -v --remove-orphans
```

Container healthcheck semantics and recovery choices: [healthchecks](../../docs/healthchecks.md).
