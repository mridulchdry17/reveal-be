# Reveal backend

API for Reveal, a college-only dating PWA where profiles are 7 cards and hidden cards open only by mutual swap. The frontend lives in `../reveal-fe` and consumes this API's OpenAPI schema.

## Commands

```bash
uv sync                                  # install
uv run fastapi dev src/main.py           # run locally on :8000
uv run pytest                            # all tests
uv run pytest tests/swaps/test_service.py -k accept   # one file / one test
uv run ruff check --fix . && uv run ruff format .     # lint + format
uv run pyright                           # type check
uv run alembic revision --autogenerate -m "add_swap_table"   # new migration
uv run alembic upgrade head              # apply migrations
docker compose up -d db                  # local Postgres on port 5433
```

A change is done when `ruff`, `pyright` and `pytest` all pass. Show the command output, not a summary of it.

## Stack (decided, don't swap without asking)

Installed: Python 3.12, uv, FastAPI, Pydantic v2 + pydantic-settings, SQLAlchemy 2 async (`AsyncSession`) + asyncpg, PostgreSQL 17, Alembic, pytest + pytest-asyncio + `httpx.AsyncClient(transport=ASGITransport(app))`, Ruff, Pyright.

Planned, add with the feature that first needs it (not before): Redis + Arq for jobs (nightly drop, push fan-out), pywebpush (VAPID) for notifications, S3-compatible private bucket for photos and voice notes.

## Layout: by domain, not by file type

```
src/
  main.py              app factory; product routers mounted under /v1
  config.py  database.py
  models.py            Base, naming convention, UUIDPrimaryKeyMixin, TimestampMixin
  exceptions.py        DomainError family + the one HTTP handler
  schemas.py           ErrorResponse (shape of every error)
  security.py          require_admin, RateLimiter / limit_by_ip
  enrollment.py        normalize() / is_valid(): the only enrollment-number rules
  health/              smallest example of the layers
  waitlist/            first product domain: copy its shape for new ones
  <domain>/            planned: auth, verification, profiles, drops, matches,
                       chats, swaps, guess, safety, notifications, moderation
    router.py          HTTP only: parse, call service, return schema
    schemas.py         Pydantic request/response models
    models.py          SQLAlchemy tables
    service.py         business rules; the only layer that decides anything
    repository.py      queries; no business rules
    dependencies.py    reusable Depends (e.g. valid_match_id, current_user)
    exceptions.py  constants.py
tests/<domain>/        mirrors src/
```

## Layers (MVCS): each file has one job

Calls go one way only: **router → service → repository → database**. A layer may call the one below it, never the one above, never skip one.

| Layer (MVCS role) | File | Does | Never does |
|---|---|---|---|
| Controller | `router.py` | Read the request, run `Depends` checks, call **one** service function, return a schema, pick the status code | Business rules, `if` on product logic, SQL, touching `AsyncSession` or models |
| View | `schemas.py` | Shape and validate data in and out; field-level rules (length, enum, format) | Query the DB, call services, know about other users |
| Service | `service.py` | All business rules and decisions (can this user swap? which cards are visible?), transactions, calling other domains' services, enqueueing jobs | SQL, `HTTPException`, reading `Request`, returning ORM objects to the router |
| Repository | `repository.py` | Build and run queries, return models or plain rows | Decide anything, raise HTTP errors, call services |
| Model | `models.py` | Table definitions, columns, relationships, constraints | Methods with business logic |
| Dependencies | `dependencies.py` | Reusable request checks: `current_user`, `valid_match_id`, `match_is_mine` (chain them) | Business decisions beyond "does it exist / is it yours" |

- Cross-domain calls go service to service through its public functions (`from src.swaps import service as swap_service`). Never import another domain's repository or models.
- Services take and return typed objects (schemas or small dataclasses), so they can be tested without HTTP.
- If a router grows past ~15 lines or has an `if` about the product, that logic belongs in the service.
- If two services need the same rule, it lives in the domain that owns that concept and the other one calls it. Don't copy it.
- Keep this tree in sync when you add a domain. Delete it from this file once the code makes it obvious.

## Product rules the code must enforce

These are the reason the product exists. Every one needs a test, and a change that touches one needs a reviewer.

1. **Visibility has one source of truth:** `profiles.service.visible_cards(viewer, owner)`. Every endpoint that returns another user's data goes through it. Never return a hidden field and rely on the frontend to hide it.
2. **No one-sided reveal.** A hidden card opens for a pair only when both have accepted the same swap. Acceptance is one transaction that opens both sides or neither.
3. **Order:** cards 1–5 swap in any order; photo (6) only after at least one card swap; contact (7) only after photo.
4. **Photo pieces:** 9 per photo. Each card swap opens 2, each correct guess opens 1, the photo swap opens all. Pieces are cut and watermarked per viewer on the server; the full image never leaves the server before the photo swap.
5. **Step away / unmatch / block revokes everything** revealed between the pair, for both, immediately.
6. **Audience filters apply both ways:** first-years see and are seen only by first-years (unless they opt out); hide list and blocks are symmetric and silent.
7. **Rank-list fields are read-only to users** (official name, branch, year, enrollment number).
8. **Selfie and ID images are deleted when review ends**, approve or reject. Store only the outcome.
9. **"Women write first"** when enabled: the other side can't send until she has.

## Conventions

- `async def` everywhere. Never call blocking I/O in an async route; wrap an unavoidable sync SDK with `run_in_threadpool`.
- Validate at the edge with Pydantic (`Field`, enums, constrained types). Services receive typed objects, not dicts.
- Domain errors are exceptions in `<domain>/exceptions.py`, mapped to HTTP in one handler in `src/exceptions.py`. Don't raise `HTTPException` from services.
- DB: singular snake_case tables, `_at` for timestamps (UTC, tz-aware), `_id` FKs, explicit `MetaData(naming_convention=...)`. Do joins and filtering in SQL, not Python loops.
- Migrations are reviewed, reversible, never edited after merge. No data backfills inside schema migrations.
- Anything that must survive a crash or retry (drop generation, push, image processing) is an Arq job, not `BackgroundTasks`.
- Every route sets `response_model` and `status_code`, and lists its error responses with `ErrorResponse`. API docs are off outside `local` and `staging`.
- Product routes live under `/v1`. A breaking change ships as a new version next to the old one, because installed PWAs keep old code cached.
- Tables use `UUIDPrimaryKeyMixin` + `TimestampMixin`. Never expose sequential ids.
- Never reveal whether someone else's data exists. If submitted details clash with another person's entry, answer exactly like a success and save nothing (see `waitlist.service.join`). On a dating app, "is she on it?" must be unanswerable.
- Admin-only routes use `Depends(require_admin)` and `include_in_schema=False`, so they never reach the frontend's generated types.
- Never log PII: no names, enrollment numbers, phone numbers, message text or image URLs. Log user ids.
- Config only via `src/config.py` settings. No `os.environ` reads elsewhere. No secrets in the repo; `.env.example` lists keys only.

## How to work here

- Before changing more than one file, state the plan: files, what changes, how it will be tested. Wait if the change touches a product rule above or a migration.
- Write the failing test first for any bug or product rule, then make it pass.
- Small diffs. Keep a refactor and a behaviour change in separate commits.
- **DRY means one place per piece of knowledge**, not "no similar-looking lines". Extract on the third repeat, not the second. A product rule duplicated in two services is a bug; two similar queries are fine.
- **KISS / YAGNI:** build for the one college in V1. No plugin systems, generic base repositories, or abstractions for a second implementation that doesn't exist.
- Prefer the boring standard FastAPI/SQLAlchemy way over a clever one. Add a dependency only if it removes real code; say why in the PR.
- When the API changes, the OpenAPI schema is the contract: tell the user the frontend needs `pnpm gen:api`.

## Gotchas

- Tests run against a real Postgres (`docker compose up -d db`), not SQLite; JSONB and timezone behaviour differ. They use a separate `reveal_test` database, created and migrated automatically by `tests/conftest.py`; tables are truncated after each test.
- `RateLimiter` is in-memory, so it's only correct with one API process. Move it to Redis before adding workers or servers.
- Reveal's Postgres is on port **5433**, not 5432: this machine already runs another Postgres on 5432. An error like `role "reveal" does not exist` means you hit the wrong one.
- New domain models must be imported in `migrations/env.py` or autogenerate won't see them.
- Override dependencies in tests with `app.dependency_overrides`, not monkeypatching.
- The drop runs at 21:00 IST (`Asia/Kolkata`); store UTC, convert only at the schedule boundary.
- The hosted database is **Azure Database for PostgreSQL** `reveal-db-eastasia` (East Asia, Burstable B1ms, free tier) in resource group `reveal`. Its URL lives only in `reveal-be/.env` (git-ignored), with `?ssl=require`. The Azure for Students subscription may deploy only in centralindia, eastasia, austriaeast, malaysiawest and koreacentral; B1ms failed with `SkuNotAvailable` in centralindia and koreacentral (Nov 2026). `scripts/try_azure_postgres.sh` recreates it if ever needed.
- With `.env` pointing at Azure, `uv run alembic upgrade head` and `fastapi dev` hit the **hosted** database. Tests are unaffected: `tests/conftest.py` forces the local `reveal_test` database.
