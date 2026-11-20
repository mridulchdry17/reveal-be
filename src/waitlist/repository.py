import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.waitlist.models import WaitlistEntry


async def find_matching(
    session: AsyncSession, enrollment_number: str, email: str
) -> list[WaitlistEntry]:
    """Entries that share the enrollment number or the email (0, 1 or 2 rows)."""
    result = await session.scalars(
        select(WaitlistEntry).where(
            or_(
                WaitlistEntry.enrollment_number == enrollment_number,
                WaitlistEntry.email == email,
            )
        )
    )
    return list(result)


async def add(session: AsyncSession, entry: WaitlistEntry) -> None:
    session.add(entry)
    await session.flush()


async def position_of(session: AsyncSession, entry_id: uuid.UUID) -> int:
    joined_at = (
        select(WaitlistEntry.created_at).where(WaitlistEntry.id == entry_id).scalar_subquery()
    )
    count = await session.scalar(
        select(func.count()).select_from(WaitlistEntry).where(WaitlistEntry.created_at <= joined_at)
    )
    return count or 0


async def list_all(session: AsyncSession) -> list[WaitlistEntry]:
    result = await session.scalars(select(WaitlistEntry).order_by(WaitlistEntry.created_at))
    return list(result)
