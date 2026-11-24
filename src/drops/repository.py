import uuid
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.drops.models import DropItem


async def lock_viewer(session: AsyncSession, viewer_id: uuid.UUID) -> None:
    """Until commit, other requests building this viewer's drop wait, so it's built once."""
    await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(str(viewer_id)))))


async def items(session: AsyncSession, viewer_id: uuid.UUID, drop_date: date) -> list[DropItem]:
    rows = await session.scalars(
        select(DropItem)
        .where(DropItem.viewer_id == viewer_id, DropItem.drop_date == drop_date)
        .order_by(DropItem.position)
    )
    return list(rows)


async def get_item(session: AsyncSession, item_id: uuid.UUID) -> DropItem | None:
    return await session.get(DropItem, item_id)


async def item_for(
    session: AsyncSession, viewer_id: uuid.UUID, shown_user_id: uuid.UUID, drop_date: date
) -> DropItem | None:
    return await session.scalar(
        select(DropItem).where(
            DropItem.viewer_id == viewer_id,
            DropItem.shown_user_id == shown_user_id,
            DropItem.drop_date == drop_date,
        )
    )


async def seen_ids(session: AsyncSession, viewer_id: uuid.UUID, since: date) -> list[uuid.UUID]:
    """Everyone shown on or after `since`, plus everyone ever liked or passed."""
    rows = await session.scalars(
        select(DropItem.shown_user_id)
        .where(
            DropItem.viewer_id == viewer_id,
            or_(DropItem.drop_date >= since, DropItem.decision.is_not(None)),
        )
        .distinct()
    )
    return list(rows)


async def add_items(session: AsyncSession, rows: list[DropItem]) -> None:
    session.add_all(rows)
    await session.flush()
