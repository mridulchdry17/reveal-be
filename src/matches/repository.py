import uuid

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.matches.models import Like, Match


async def get_like(
    session: AsyncSession, from_user_id: uuid.UUID, to_user_id: uuid.UUID
) -> Like | None:
    return await session.scalar(
        select(Like).where(Like.from_user_id == from_user_id, Like.to_user_id == to_user_id)
    )


async def get_like_by_id(session: AsyncSession, like_id: uuid.UUID) -> Like | None:
    return await session.get(Like, like_id)


async def likes_to(session: AsyncSession, user_id: uuid.UUID, status: str) -> list[Like]:
    rows = await session.scalars(
        select(Like)
        .where(Like.to_user_id == user_id, Like.status == status)
        .order_by(Like.created_at.desc())
    )
    return list(rows)


async def add_like(session: AsyncSession, like: Like) -> None:
    session.add(like)
    await session.flush()


async def add_match(session: AsyncSession, user_a_id: uuid.UUID, user_b_id: uuid.UUID) -> None:
    """Idempotent: if both liked back at the same moment, the pair still matches once."""
    await session.execute(
        insert(Match)
        .values(id=uuid.uuid4(), user_a_id=user_a_id, user_b_id=user_b_id)
        .on_conflict_do_nothing(index_elements=["user_a_id", "user_b_id"])
    )


async def connected_ids(session: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    """Everyone with a like in either direction. Every match starts from a like."""
    rows = await session.execute(
        select(Like.from_user_id, Like.to_user_id).where(
            or_(Like.from_user_id == user_id, Like.to_user_id == user_id)
        )
    )
    return [b if a == user_id else a for a, b in rows]
