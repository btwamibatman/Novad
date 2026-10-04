from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.core.config import settings


def check_database_ready() -> None:
    # Keep probes independent of the application's connection pool. PostgreSQL
    # connection and query timeouts also bound failures during an outage.
    connect_args = {}
    if settings.database_url.startswith("postgresql"):
        connect_args = {"connect_timeout": 2, "options": "-c statement_timeout=2000"}
    engine = create_engine(
        settings.database_url, poolclass=NullPool, connect_args=connect_args,
    )
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    finally:
        engine.dispose()
