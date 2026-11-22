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
  auth/                Google sign-in, bearer sessions (hashed), current_user / admin_user
  verification/        ID card + selfie review requests; photos as files (storage.py)
  admin/               review queue, approve/reject, let someone in, action log
  profiles/            basics, 3 prompts, 7 cards, preferences; what others may see; drop audience
  drops/               tonight's drop: 5 profiles a night at 9 PM, like a prompt or pass
  matches/             likes (Likes list, match back, pass) and matches
  clock.py             now() as a dependency, so tests can set the time
  <domain>/            planned: chats, swaps, guess, safety, notifications, moderation
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

1. **Visibility has one source of truth:** `profiles.service.public_profiles(viewer, owners)`. Every endpoint that returns another user's data goes through it. Never return a hidden field and rely on the frontend to hide it.
2. **No one-sided reveal.** A hidden card opens for a pair only when both have accepted the same swap. Acceptance is one transaction that opens both sides or neither.
3. **Order:** cards 1–5 swap in any order; photo (6) only after at least one card swap; contact (7) only after photo.
4. **Photo pieces:** 9 per photo. Each card swap opens 2, each correct guess opens 1, the photo swap opens all. Pieces are cut and watermarked per viewer on the server; the full image never leaves the server before the photo swap.
5. **Step away / unmatch / block revokes everything** revealed between the pair, for both, immediately.
6. **Audience filters apply both ways:** someone appears in your drop only if their gender is in your "Interested in" and yours is in theirs. Year never limits who you see ("Match me on" only ranks). Hide list and blocks are symmetric and silent.
7. **Verified fields are read-only to users** (official name, branch, year, enrollment number). They're set when a student is verified (college Google account, ID card review, or an admin letting them in) and only admins can change them. One account per enrollment number and per college email.
8. **Selfie and ID images are deleted when review ends**, approve or reject. Store only the outcome.
9. **Either person can write first** after a match. "Women write first" was removed on purpose (Nov 2026); don't add it back without asking.

## Conventions

- `async def` everywhere. Never call blocking I/O in an async route; wrap an unavoidable sync SDK with `run_in_threadpool`.
- Validate at the edge with Pydantic (`Field`, enums, constrained types). Services receive typed objects, not dicts.
- Domain errors are exceptions in `<domain>/exceptions.py`, mapped to HTTP in one handler in `src/exceptions.py`. Don't raise `HTTPException` from services.
- DB: singular snake_case tables, `_at` for timestamps (UTC, tz-aware), `_id` FKs, explicit `MetaData(naming_convention=...)`. Do joins and filtering in SQL, not Python loops.
- Migrations are reviewed, reversible, never edited after merge. No data backfills inside schema migrations.
- Anything that must survive a crash or retry (push, image processing) is an Arq job, not `BackgroundTasks`. Exception for now: the drop is built on the first `GET /v1/drops/tonight` after 9 PM and saved (`drop_item`), under a per-viewer advisory lock, and tops up while it has fewer than 5. No Redis/worker until push needs a 9 PM job; `drops.service` stays the one place that picks who's in a drop.
- Drops and likes: `drops.service` asks `profiles.service.drop_candidates` (audience both ways, best fit first) and excludes anyone shown in the last 14 days, ever liked or passed, or with a like either way (`matches.service.connected_ids`). Liking copies the prompt text into `profile_like`; a like back (from the Likes list or the other's drop) creates one `match` row per pair. Passing is silent: the liker is never told. Use `src.clock.now` for the time, never `datetime.now()` in services.
- Every route sets `response_model` and `status_code`, and lists its error responses with `ErrorResponse`. API docs are off outside `local` and `staging`.
- Product routes live under `/v1`. A breaking change ships as a new version next to the old one, because installed PWAs keep old code cached.
- Tables use `UUIDPrimaryKeyMixin` + `TimestampMixin`. Never expose sequential ids.
- Never reveal whether someone else's data exists. If submitted details clash with another person's entry, answer exactly like a success and save nothing (see `waitlist.service.join`). On a dating app, "is she on it?" must be unanswerable.
- Signed-in routes use `Depends(current_user)`; admin screens use `Depends(admin_user)` (admins = `ADMIN_EMAILS`). The older `require_admin` (`X-Admin-Token`) is only for scripts like the waitlist CSV export; those routes use `include_in_schema=False`, so they never reach the frontend's generated types.
- Sign-in: the frontend sends Google's ID token to `POST /v1/auth/google`; we verify it with `google-auth` and return an opaque session token (stored only as SHA-256). Any Google account can sign in; being a verified student is a separate step. Tests override `get_google_verifier`, never call Google.
- Student verification lives on `user_account` (`verified_via`, `verified_at`, `college_email`); other domains set it only through `auth.service`. College email: `POST /v1/auth/college-email` takes a credential for the user's college Google account and trusts only Google's `hd` claim (`settings.college_domain`), never the address alone. Signing in with a college account verifies straight away.
- ID card verification: `POST /v1/verification/id-card` (multipart selfie + id_card) stores both photos as files in `settings.verification_photos_dir` (mode 600, random names, type checked from the bytes) and a `verification_request` row. Photos are deleted on review and after `verification_photo_days` unreviewed (swept on each upload). On servers the folder is `/var/lib/reveal/<env>/verification`, outside the checkout, so deploys never touch it. Never serve that folder; admins read photos only through the API.
- Product endpoints use `verified_user` (signed in and verified). Profiles: `/v1/profile/me` plus one PUT per profile screen; free text that others see goes through `profiles.text_rules.has_contact_info` (numbers, handles, links belong on card 7). Choices live in `profiles/constants.py` and reach the frontend via `GET /v1/profile/options`.
- Admin (`/v1/admin/*`, `admin_user`): approve/reject a review (photos deleted after commit), let a signed-in account in by email, and every decision lands in `admin_action`. Decisions span domains in one transaction: `verification.service.decide` and `auth.service.mark_verified` don't commit; `admin.service` does.
- Never log PII: no names, enrollment numbers, phone numbers, message text or image URLs. Log user ids.
- Config only via `src/config.py` settings. No `os.environ` reads elsewhere. No secrets in the repo; `.env.example` lists keys only.

## How to work here

- **Branches:** `pre-release` is the default branch. Feature branches open PRs into `pre-release`; deploy staging and test there. Release = a PR from `pre-release` into `main`, then deploy production. Never commit or merge straight to `main`. Merge PRs with merge commits, never squash.

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
- With `.env` pointing at Azure, `uv run alembic upgrade head` and `fastapi dev` hit the **hosted production** database (from a laptop they usually just time out at the firewall). For local migrations and autogenerate, prefix `DATABASE_URL=postgresql+asyncpg://reveal:reveal@localhost:5433/reveal`. Tests are unaffected: `tests/conftest.py` forces the local `reveal_test` database.
- Production runs on the Azure VM (`azureuser@40.82.143.50`, key `~/.ssh/id_ed25519_reveal_vm`) as systemd `reveal-api` on 127.0.0.1:8001 behind Caddy at `reveal-api.koreacentral.cloudapp.azure.com`. Staging runs beside it as `reveal-api-staging` on :8002 (checkout `~/reveal-be-staging`, branch `pre-release`, database `reveal_staging`), served at `/staging`. Deploys are manual: `deploy/deploy.sh staging|production` on the VM (see README "Environments"). The VM has <1 GB RAM: keep one uvicorn worker per environment and don't add services casually. Never print or commit the VM's `.env` files.
