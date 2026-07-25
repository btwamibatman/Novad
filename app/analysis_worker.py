from __future__ import annotations

import logging
import time

from app.core.config import settings
from app.core.database import init_db
from app.services.analysis_jobs import run_next_analysis_job

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_worker() -> None:
    init_db()
    logger.info("Analysis worker started")
    while True:
        try:
            processed = run_next_analysis_job()
        except Exception:
            logger.exception("Analysis worker iteration failed")
            processed = False
        if not processed:
            time.sleep(settings.analysis_worker_poll_seconds)


if __name__ == "__main__":
    run_worker()
