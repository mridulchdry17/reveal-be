import uuid
from pathlib import Path
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from src.admin import repository
from src.admin.constants import AdminActionKind
from src.admin.exceptions import AccountNotFound, AlreadyVerified
from src.admin.models import AdminAction
from src.admin.schemas import AdminActionOut, LetInResult, Review, ReviewUser
from src.auth import service as auth_service
from src.auth.constants import VerificationMethod
from src.auth.schemas import Me
from src.verification import service as verification_service


async def reviews(session: AsyncSession) -> list[Review]:
    pending = await verification_service.pending_reviews(session)
    users = await auth_service.accounts(session, [p.user_id for p in pending])
    return [
        Review(
            id=p.id,
            user=ReviewUser(id=u.id, name=u.name, email=u.email),
            submitted_at=p.submitted_at,
        )
        for p in pending
        if (u := users.get(p.user_id))
    ]


async def photo(
    session: AsyncSession, review_id: uuid.UUID, kind: Literal["selfie", "id_card"]
) -> Path:
    return await verification_service.photo_path(session, review_id, kind)


async def approve(session: AsyncSession, admin: Me, review_id: uuid.UUID) -> None:
    """The ID and selfie match: they're a verified student. Photos are deleted."""
    decision = await verification_service.decide(session, review_id, approve=True)
    await auth_service.mark_verified(session, decision.user_id, VerificationMethod.ID_CARD)
    await _log(session, admin, AdminActionKind.APPROVE, decision.user_id)
    await session.commit()
    await verification_service.delete_photos(decision.files)


async def reject(session: AsyncSession, admin: Me, review_id: uuid.UUID, reason: str) -> None:
    """Not verified; they see the reason and can send new photos. Photos are deleted."""
    decision = await verification_service.decide(session, review_id, approve=False, reason=reason)
    await _log(session, admin, AdminActionKind.REJECT, decision.user_id, note=reason)
    await session.commit()
    await verification_service.delete_photos(decision.files)


async def let_in(session: AsyncSession, admin: Me, email: str, note: str | None) -> LetInResult:
    """Verify someone without an email or ID check, e.g. a first-year. They must sign in first."""
    account = await auth_service.find_account(session, email)
    if account is None:
        raise AccountNotFound("No Reveal account with that email. Ask them to sign in first.")
    if account.verified:
        raise AlreadyVerified("They're already verified")
    await auth_service.mark_verified(session, account.id, VerificationMethod.ADMIN)
    await _log(session, admin, AdminActionKind.LET_IN, account.id, note=note)
    await session.commit()
    return LetInResult(id=account.id, name=account.name, email=account.email)


async def recent_actions(session: AsyncSession, limit: int = 100) -> list[AdminActionOut]:
    return [
        AdminActionOut(
            id=a.id,
            action=AdminActionKind(a.action),
            admin_email=a.admin_email,
            target_email=a.target_email,
            note=a.note,
            created_at=a.created_at,
        )
        for a in await repository.recent(session, limit)
    ]


async def _log(
    session: AsyncSession,
    admin: Me,
    action: AdminActionKind,
    user_id: uuid.UUID,
    note: str | None = None,
) -> None:
    users = await auth_service.accounts(session, [user_id])
    target = users.get(user_id)
    await repository.add(
        session,
        AdminAction(
            admin_email=admin.email,
            action=action,
            target_user_id=user_id,
            target_email=target.email if target else "",
            note=note,
        ),
    )
