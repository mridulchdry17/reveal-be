import asyncio
import os
from collections.abc import AsyncIterator, Iterator

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

# Point the app at a separate test database before anything imports src.config.
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://reveal:reveal@localhost:5433/reveal_test"
)
os.environ["ADMIN_TOKEN"] = "test-admin-token"
os.environ["ADMIN_EMAILS"] = '["admin@gmail.com"]'

from src.auth.dependencies import sign_in_limiter
from src.config import settings
from src.database import engine
from src.main import app
from src.models import Base
from src.profiles.dependencies import media_upload_limiter
from src.verification.dependencies import upload_limiter
from src.waitlist.dependencies import join_limiter

ADMIN_HEADERS = {"X-Admin-Token": "test-admin-token"}


async def _create_test_database() -> None:
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    server_url, db_name = url.rsplit("/", 1)
    conn = await asyncpg.connect(f"{server_url}/postgres")
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db_name)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
def _database() -> Iterator[None]:
    """Create the test database and run the real migrations once per session."""
    asyncio.run(_create_test_database())
    command.upgrade(Config("alembic.ini"), "head")
    yield


@pytest.fixture(autouse=True)
def _photos_dir(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Uploaded photos (verification and profile) go to a fresh temporary folder per test."""
    monkeypatch.setattr(settings, "verification_photos_dir", str(tmp_path / "photos"))
    monkeypatch.setattr(settings, "media_dir", str(tmp_path / "media"))
    monkeypatch.setattr(settings, "media_storage_account", "")


@pytest.fixture(autouse=True)
async def _clean_state() -> AsyncIterator[None]:
    yield
    join_limiter.reset()
    media_upload_limiter.reset()
    sign_in_limiter.reset()
    upload_limiter.reset()
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    if tables:
        async with engine.begin() as conn:
            await conn.execute(text(f"TRUNCATE {tables} CASCADE"))


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
