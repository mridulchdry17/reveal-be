import uuid
from collections.abc import Sequence

from sqlalchemy import and_, or_, select
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


async def get_like_for_update(session: AsyncSession, like_id: uuid.UUID) -> Like | None:
    """Locked until commit, so an answer and a take-back can't cross."""
    return await session.scalar(select(Like).where(Like.id == like_id).with_for_update())


async def likes_from(
    session: AsyncSession, user_id: uuid.UUID, statuses: Sequence[str]
) -> list[Like]:
    rows = await session.scalars(
        select(Like)
        .where(Like.from_user_id == user_id, Like.status.in_(statuses))
        .order_by(Like.created_at.desc())
    )
    return list(rows)


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


async def add_match(session: AsyncSession, user_a_id: uuid.UUID, user_b_id: uuid.UUID) -> uuid.UUID:
    """Idempotent: if both liked back at the same moment, the pair still matches once.

    Returns the pair's match id either way."""
    await session.execute(
        insert(Match)
        .values(id=uuid.uuid4(), user_a_id=user_a_id, user_b_id=user_b_id)
        .on_conflict_do_nothing(index_elements=["user_a_id", "user_b_id"])
    )
    found = await session.execute(
        select(Match.id).where(Match.user_a_id == user_a_id, Match.user_b_id == user_b_id)
    )
    return found.scalar_one()


def _mine(user_id: uuid.UUID):
    return and_(
        or_(Match.user_a_id == user_id, Match.user_b_id == user_id), Match.ended_at.is_(None)
    )


async def live_matches(session: AsyncSession, user_id: uuid.UUID) -> list[Match]:
    rows = await session.scalars(select(Match).where(_mine(user_id)))
    return list(rows)


async def live_match(
    session: AsyncSession, user_id: uuid.UUID, match_id: uuid.UUID
) -> Match | None:
    return await session.scalar(select(Match).where(Match.id == match_id, _mine(user_id)))


async def live_match_between(
    session: AsyncSession, user_id: uuid.UUID, other_id: uuid.UUID
) -> Match | None:
    a, b = sorted((user_id, other_id))
    return await session.scalar(
        select(Match).where(Match.user_a_id == a, Match.user_b_id == b, Match.ended_at.is_(None))
    )


async def connected_ids(session: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    """Everyone with a like in either direction. Every match starts from a like."""
    rows = await session.execute(
        select(Like.from_user_id, Like.to_user_id).where(
            or_(Like.from_user_id == user_id, Like.to_user_id == user_id)
        )
    )
    return [b if a == user_id else a for a, b in rows]
