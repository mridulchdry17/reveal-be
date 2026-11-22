import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.schemas import Me
from src.config import settings
from src.verification import repository, storage
from src.verification.constants import RequestStatus
from src.verification.exceptions import (
    AlreadyReviewed,
    AlreadySubmitted,
    AlreadyVerified,
    NotAPhoto,
    PhotoTooLarge,
    ReviewNotFound,
)
from src.verification.models import VerificationRequest
from src.verification.schemas import VerificationStatus


@dataclass(frozen=True)
class PendingReview:
    id: uuid.UUID
    user_id: uuid.UUID
    submitted_at: datetime


@dataclass(frozen=True)
class Decision:
    user_id: uuid.UUID
    # Delete these once the decision is committed.
    files: tuple[str | None, ...]


async def status_for(session: AsyncSession, user_id: uuid.UUID) -> VerificationStatus:
    row = await repository.get_for_user(session, user_id)
    if row is None:
        return VerificationStatus(status=RequestStatus.NONE)
    return _to_status(row)


async def submit_id_card(
    session: AsyncSession, user: Me, selfie: bytes, id_card: bytes
) -> VerificationStatus:
    """Store the ID card and selfie for an admin to check against each other."""
    if user.verified:
        raise AlreadyVerified("You're already verified")
    selfie_ext = _check_photo(selfie, "selfie")
    id_card_ext = _check_photo(id_card, "ID card")

    await purge_expired(session)
    row = await repository.get_for_user(session, user.id)
    if row is not None and row.status == RequestStatus.PENDING:
        raise AlreadySubmitted("Your photos are already waiting for review")

    old_files = (row.selfie_file, row.id_card_file) if row else (None, None)
    if row is None:
        row = VerificationRequest(
            user_id=user.id, status=RequestStatus.PENDING, submitted_at=datetime.now(UTC)
        )
        await repository.add(session, row)

    saved: list[str] = []
    try:
        saved.append(await storage.save(row.id, "selfie", selfie, selfie_ext))
        saved.append(await storage.save(row.id, "id", id_card, id_card_ext))
        row.selfie_file, row.id_card_file = saved
        row.status = RequestStatus.PENDING
        row.submitted_at = datetime.now(UTC)
        row.reviewed_at = None
        row.reject_reason = None
        await session.commit()
    except BaseException:
        # No row points at these files, so don't leave them on disk.
        await storage.delete(*saved)
        raise
    await storage.delete(*old_files)
    return _to_status(row)


async def purge_expired(session: AsyncSession) -> int:
    """Delete photos nobody reviewed in time. Returns how many requests expired."""
    cutoff = datetime.now(UTC) - timedelta(days=settings.verification_photo_days)
    rows = await repository.pending_submitted_before(session, cutoff)
    for row in rows:
        await storage.delete(row.selfie_file, row.id_card_file)
        row.status = RequestStatus.EXPIRED
        row.selfie_file = None
        row.id_card_file = None
    if rows:
        await session.commit()
    return len(rows)


async def pending_reviews(session: AsyncSession) -> list[PendingReview]:
    """Oldest first, so nobody waits longest."""
    await purge_expired(session)
    return [
        PendingReview(id=r.id, user_id=r.user_id, submitted_at=r.submitted_at)
        for r in await repository.list_pending(session)
    ]


async def photo_path(
    session: AsyncSession, request_id: uuid.UUID, kind: Literal["selfie", "id_card"]
) -> Path:
    row = await repository.get(session, request_id)
    name = (row.selfie_file if kind == "selfie" else row.id_card_file) if row else None
    if name is None or not storage.path_for(name).is_file():
        raise ReviewNotFound("Photo not found")
    return storage.path_for(name)


async def decide(
    session: AsyncSession, request_id: uuid.UUID, approve: bool, reason: str | None = None
) -> Decision:
    """Record an admin's decision. Doesn't commit; delete the returned files after commit."""
    row = await repository.get(session, request_id)
    if row is None:
        raise ReviewNotFound("No such review")
    if row.status != RequestStatus.PENDING:
        raise AlreadyReviewed("Someone already reviewed this")
    files = (row.selfie_file, row.id_card_file)
    row.status = RequestStatus.APPROVED if approve else RequestStatus.REJECTED
    row.reject_reason = None if approve else reason
    row.reviewed_at = datetime.now(UTC)
    row.selfie_file = None
    row.id_card_file = None
    await session.flush()
    return Decision(user_id=row.user_id, files=files)


async def delete_photos(files: tuple[str | None, ...]) -> None:
    await storage.delete(*files)


def _check_photo(data: bytes, label: str) -> str:
    if len(data) > settings.verification_photo_max_bytes:
        raise PhotoTooLarge(f"The {label} photo is too large")
    extension = storage.detect_image_type(data)
    if extension is None:
        raise NotAPhoto(f"The {label} file isn't a JPEG, PNG or WebP photo")
    return extension


def _to_status(row: VerificationRequest) -> VerificationStatus:
    return VerificationStatus(
        status=RequestStatus(row.status),
        submitted_at=row.submitted_at,
        reject_reason=row.reject_reason,
    )
