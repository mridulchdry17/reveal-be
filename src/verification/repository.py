import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.verification.constants import RequestStatus
from src.verification.models import VerificationRequest


async def get_for_user(session: AsyncSession, user_id: uuid.UUID) -> VerificationRequest | None:
    return await session.scalar(
        select(VerificationRequest).where(VerificationRequest.user_id == user_id)
    )


async def pending_submitted_before(
    session: AsyncSession, cutoff: datetime
) -> list[VerificationRequest]:
    rows = await session.scalars(
        select(VerificationRequest).where(
            VerificationRequest.status == RequestStatus.PENDING,
            VerificationRequest.submitted_at < cutoff,
        )
    )
    return list(rows)


async def add(session: AsyncSession, row: VerificationRequest) -> None:
    session.add(row)
    await session.flush()
