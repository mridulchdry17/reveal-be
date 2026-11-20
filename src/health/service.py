from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.health import repository
from src.health.schemas import HealthResponse


async def check(session: AsyncSession) -> HealthResponse:
    try:
        await repository.ping(session)
    except (SQLAlchemyError, OSError):
        return HealthResponse(status="degraded", database="down")
    return HealthResponse(status="ok", database="ok")
