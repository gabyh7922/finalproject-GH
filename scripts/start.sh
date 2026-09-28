#!/bin/sh
# Arranque en producción: migraciones -> ingesta (solo si la tabla está vacía) -> API.
set -e
uv run --no-dev alembic upgrade head
uv run --no-dev python scripts/ingest.py --if-empty
exec uv run --no-dev uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="*"
