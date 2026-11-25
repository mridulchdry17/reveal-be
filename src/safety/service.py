"""Block and report. Both end the match for both people at once, silently."""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.schemas import Me
from src.matches import service as match_service
from src.profiles import service as profile_service
from src.safety import repository
from src.safety.models import Report
from src.safety.schemas import BlockedOut, ReportOut, ReportRequest


async def block(session: AsyncSession, user: Me, match_id: uuid.UUID, now: datetime) -> None:
    match = await match_service.end(session, user.id, match_id, now)
    await repository.add_block(session, user.id, match.other_user_id)
    await session.commit()


async def report(
    session: AsyncSession, user: Me, match_id: uuid.UUID, body: ReportRequest, now: datetime
) -> None:
    match = await match_service.end(session, user.id, match_id, now)
    await repository.add_block(session, user.id, match.other_user_id)
    await repository.add_report(
        session,
        Report(
            reporter_id=user.id,
            reported_id=match.other_user_id,
            match_id=match.id,
            reason=body.reason,
            details=body.details,
        ),
    )
    await session.commit()


async def my_blocks(session: AsyncSession, user: Me) -> list[BlockedOut]:
    """People I blocked, latest first. Only ever shown to the blocker."""
    blocks = await repository.blocks_by(session, user.id)
    names = await profile_service.nicknames(session, [b.blocked_id for b in blocks])
    return [
        BlockedOut(id=b.id, nickname=names[b.blocked_id], blocked_at=b.created_at) for b in blocks
    ]


async def recent_reports(session: AsyncSession, limit: int = 100) -> list[ReportOut]:
    return [
        ReportOut.model_validate(r, from_attributes=True)
        for r in await repository.recent_reports(session, limit)
    ]
