# Alembic Migration Notes

Alembic is configured in this project through `alembic.ini` and `alembic/env.py`.
The migration environment reads `settings.database_url` and imports the SQLAlchemy
metadata from `app.core.database.Base`.

## Apply migrations

```bash
alembic upgrade head
```

The migration chain adds browser sessions, document chunks, content/layout review
fields and extraction-quality metadata. Existing documents are preserved and assigned
to a generated legacy session during the first upgrade.

## Create a new migration

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

`Base.metadata.create_all()` is still used for lightweight local/test database
initialization, but existing databases should be changed with Alembic migrations.
