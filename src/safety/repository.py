import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.safety.models import Block, Report


async def add_block(session: AsyncSession, blocker_id: uuid.UUID, blocked_id: uuid.UUID) -> None:
    await session.execute(
        insert(Block)
        .values(id=uuid.uuid4(), blocker_id=blocker_id, blocked_id=blocked_id)
        .on_conflict_do_nothing(index_elements=["blocker_id", "blocked_id"])
    )


async def blocks_by(session: AsyncSession, blocker_id: uuid.UUID) -> list[Block]:
    rows = await session.scalars(
        select(Block).where(Block.blocker_id == blocker_id).order_by(Block.created_at.desc())
    )
    return list(rows)


async def add_report(session: AsyncSession, report: Report) -> None:
    session.add(report)
    await session.flush()


async def recent_reports(session: AsyncSession, limit: int) -> list[Report]:
    rows = await session.scalars(select(Report).order_by(Report.created_at.desc()).limit(limit))
    return list(rows)
