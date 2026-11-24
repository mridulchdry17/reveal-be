import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.swaps.constants import SwapStatus
from src.swaps.models import Swap


async def lock_match(session: AsyncSession, match_id: uuid.UUID) -> None:
    """Until commit, other swap changes in this match wait, so two answers can't cross."""
    await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"swap:{match_id}"))))


async def open_swaps(session: AsyncSession, match_ids: Sequence[uuid.UUID]) -> list[Swap]:
    """Pending and accepted swaps of these matches."""
    rows = await session.scalars(
        select(Swap).where(
            Swap.match_id.in_(match_ids),
            Swap.status.in_([SwapStatus.PENDING, SwapStatus.ACCEPTED]),
        )
    )
    return list(rows)


async def add(session: AsyncSession, swap: Swap) -> None:
    session.add(swap)
    await session.flush()
