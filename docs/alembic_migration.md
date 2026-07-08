# Alembic Migration Notes

Alembic is configured in this project through `alembic.ini` and `alembic/env.py`.
The migration environment reads `settings.database_url` and imports the SQLAlchemy
metadata from `app.core.database.Base`.

## Apply migrations

```bash
alembic upgrade head
```

The first migration adds browser sessions and links documents to a session.
Existing documents are assigned to a generated legacy session during upgrade.

## Create a new migration

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

`Base.metadata.create_all()` is still used for lightweight local/test database
initialization, but existing databases should be changed with Alembic migrations.
