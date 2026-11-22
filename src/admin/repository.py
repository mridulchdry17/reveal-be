from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.admin.models import AdminAction


async def add(session: AsyncSession, row: AdminAction) -> None:
    session.add(row)
    await session.flush()


async def recent(session: AsyncSession, limit: int) -> list[AdminAction]:
    rows = await session.scalars(
        select(AdminAction).order_by(AdminAction.created_at.desc()).limit(limit)
    )
    return list(rows)
