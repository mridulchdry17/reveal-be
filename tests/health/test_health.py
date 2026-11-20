from typing import cast

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.health import service


async def test_health_ok_when_database_is_up(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


class _DownSession:
    async def execute(self, *_: object) -> None:
        raise ConnectionRefusedError


async def test_health_degraded_when_database_is_down() -> None:
    result = await service.check(cast(AsyncSession, _DownSession()))

    assert result.status == "degraded"
    assert result.database == "down"
