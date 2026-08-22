from __future__ import annotations

import logging
import time

from app.core.config import settings
from app.core.database import init_db
from app.services.analysis_jobs import run_next_analysis_job
from app.services.ai.jobs import run_next_ai_job
from app.services.tool_jobs import run_next_tool_job

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_worker() -> None:
    init_db()
    logger.info("Document processing worker started")
    while True:
        try:
            analysis_processed = run_next_analysis_job()
            tool_processed = run_next_tool_job()
            ai_processed = run_next_ai_job()
            processed = analysis_processed or tool_processed or ai_processed
        except Exception:
            logger.exception("Document processing worker iteration failed")
            processed = False
        if not processed:
            time.sleep(settings.analysis_worker_poll_seconds)


if __name__ == "__main__":
    run_worker()
