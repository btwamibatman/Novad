# Alembic Migration Plan

1. Install Alembic:
   `pip install alembic`
2. Initialize migrations:
   `alembic init alembic`
3. Configure `alembic/env.py` to import `Base` and `settings.database_url`.
4. Create the first migration:
   `alembic revision --autogenerate -m "initial"`
5. Apply migrations:
   `alembic upgrade head`
6. Remove `_apply_small_schema_updates()` from `app/core/database.py`.
