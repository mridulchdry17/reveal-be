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

## Environments

| | Production | Staging |
|---|---|---|
| Branch | `main` | `pre-release` |
| API | https://reveal-api.koreacentral.cloudapp.azure.com | https://reveal-api.koreacentral.cloudapp.azure.com/staging |
| Frontend | https://tryreveal.vercel.app | the `pre-release` preview on Vercel |
| VM checkout | `~/reveal-be` | `~/reveal-be-staging` |
| Service | `reveal-api` on 127.0.0.1:8001 | `reveal-api-staging` on 127.0.0.1:8002 |
| Database | `reveal` | `reveal_staging` (same Azure server) |

- Both run on the Azure VM `mridul` (Korea Central) behind Caddy (auto HTTPS); Caddy sends `/staging/*` to staging. Files in `deploy/`.
- Database server: Azure Database for PostgreSQL `reveal-db-eastasia` (East Asia).
- Flow: feature branch → PR into `pre-release` → deploy staging and test → PR `pre-release` → `main` → deploy production.
- Tests run on every PR and on pushes to `main` and `pre-release` (GitHub Actions). Deploys are manual:
  - Staging: `ssh -i ~/.ssh/id_ed25519_reveal_vm azureuser@40.82.143.50 'bash ~/reveal-be-staging/deploy/deploy.sh staging'`
  - Production: `ssh -i ~/.ssh/id_ed25519_reveal_vm azureuser@40.82.143.50 'bash ~/reveal-be/deploy/deploy.sh production'`
- Logs: `ssh ... 'sudo journalctl -u reveal-api -f'` (or `reveal-api-staging`)
- Settings live only in each checkout's `.env` on the VM (never in git).
