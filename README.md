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

## Production

- API: https://reveal-api.koreacentral.cloudapp.azure.com (Azure VM `mridul`, Korea Central)
- Database: Azure Database for PostgreSQL `reveal-db-eastasia` (East Asia)
- Runs as systemd service `reveal-api` on 127.0.0.1:8001 behind Caddy (auto HTTPS). Files in `deploy/`.
- Every PR and push to `main` runs the tests (GitHub Actions). Deploys are manual for now (command below).
- Manual deploy: `ssh -i ~/.ssh/id_ed25519_reveal_vm azureuser@40.82.143.50 'bash ~/reveal-be/deploy/deploy.sh'`
- Logs: `ssh ... 'sudo journalctl -u reveal-api -f'`
- Production settings live only in `/home/azureuser/reveal-be/.env` on the VM (never in git).
