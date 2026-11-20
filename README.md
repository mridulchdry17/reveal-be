# reveal-be

API for Reveal. FastAPI + PostgreSQL. See `CLAUDE.md` for conventions.

## Run locally

```bash
uv sync
docker compose up -d db          # Postgres on localhost:5433
uv run alembic upgrade head
uv run fastapi dev src/main.py   # http://localhost:8000/docs
```

## Check

```bash
uv run ruff check . && uv run pyright && uv run pytest
```
