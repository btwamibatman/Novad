# Container health checks

Compose defines the probes because API and worker share one image. No extra
packages are installed: PostgreSQL uses `pg_isready`, API/worker use Python,
and the development Vite service uses Node's built-in `fetch`.

| Service | Probe | Interval | Timeout | Retries | Start period |
| --- | --- | --- | --- | --- | --- |
| db | `pg_isready` | 5s | 5s | 5 | 30s |
| api | HTTP `/ready`, including `SELECT 1` | 10s | 5s | 3 | 60s |
| analysis-worker | File heartbeat | 10s | 5s | 3 | 60s |
| frontend (development) | HTTP Vite root | 10s | 5s | 3 | 120s |

`/health` is API liveness and remains HTTP 200 during a database outage.
`/ready` returns HTTP 503 when the database cannot be reached. PostgreSQL
connection and query timeouts are each two seconds; the HTTP probe has a
four-second timeout. Neither endpoint contacts Ollama or Gemini.

The worker touches `/tmp/novad-worker-heartbeat` every ten seconds, after database
initialization. This file lives in the container's writable layer, not the shared
document storage or database. A timestamp older than sixty seconds fails the
probe; Docker marks the worker unhealthy after three failed probes (typically
within about ninety seconds of a freeze, after the start period). A separate
thread keeps legitimate long OCR/AI jobs healthy. This proves process liveness,
not queue throughput or database availability; the smoke test checks processing.
Clock jumps can temporarily fail this timestamp-based check.

Stopping a container produces `exited`, not `unhealthy`: Docker no longer runs
probes in stopped containers. To verify a frozen worker, send `SIGSTOP` to its
Python process while leaving the container running, then restore it with `SIGCONT`.
Do not use `docker pause`, which also prevents probe execution.

Health checks do not restart containers. No restart policy or autoheal is added.
Possible separate follow-ups are alerting with manual recovery, a restart policy
for process exits (which still ignores unhealthy status), or an orchestrator with
explicit liveness/recovery rules. Automatic recovery needs a separate decision
about interrupted jobs and duplicate processing.
