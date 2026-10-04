from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from threading import Event, Thread
import time

HEARTBEAT_PATH = Path("/tmp/novad-worker-heartbeat")
HEARTBEAT_INTERVAL_SECONDS = 10
HEARTBEAT_MAX_AGE_SECONDS = 60


def heartbeat_is_fresh(path: Path = HEARTBEAT_PATH) -> bool:
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        return False
    return 0 <= age <= HEARTBEAT_MAX_AGE_SECONDS


@contextmanager
def worker_heartbeat(path: Path = HEARTBEAT_PATH):
    stopped = Event()

    def update() -> None:
        # A separate thread keeps long OCR/AI jobs from failing a liveness probe.
        while not stopped.wait(HEARTBEAT_INTERVAL_SECONDS):
            path.touch()

    path.touch()
    thread = Thread(target=update, name="worker-heartbeat", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join()
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(0 if heartbeat_is_fresh() else 1)
