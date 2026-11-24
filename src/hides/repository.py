import uuid
from collections.abc import Collection

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.hides.models import HiddenContact


async def list_for(session: AsyncSession, owner_id: uuid.UUID) -> list[HiddenContact]:
    rows = await session.scalars(
        select(HiddenContact)
        .where(HiddenContact.owner_id == owner_id)
        .order_by(HiddenContact.created_at.desc())
    )
    return list(rows)


async def count_for(session: AsyncSession, owner_id: uuid.UUID) -> int:
    found = await session.scalar(select(func.count()).where(HiddenContact.owner_id == owner_id))
    return found or 0


async def add(
    session: AsyncSession, owner_id: uuid.UUID, kind: str, fingerprint: str, hint: str
) -> None:
    await session.execute(
        insert(HiddenContact)
        .values(id=uuid.uuid4(), owner_id=owner_id, kind=kind, fingerprint=fingerprint, hint=hint)
        .on_conflict_do_nothing(index_elements=["owner_id", "fingerprint"])
    )


async def remove(session: AsyncSession, owner_id: uuid.UUID, entry_id: uuid.UUID) -> bool:
    result = await session.execute(
        delete(HiddenContact)
        .where(HiddenContact.id == entry_id, HiddenContact.owner_id == owner_id)
        .returning(HiddenContact.id)
    )
    return result.scalar() is not None


async def fingerprints_of(session: AsyncSession, owner_id: uuid.UUID) -> list[str]:
    rows = await session.scalars(
        select(HiddenContact.fingerprint).where(HiddenContact.owner_id == owner_id)
    )
    return list(rows)


async def owners_hiding(session: AsyncSession, fingerprints: Collection[str]) -> list[uuid.UUID]:
    """Everyone whose list has any of these fingerprints."""
    if not fingerprints:
        return []
    rows = await session.scalars(
        select(HiddenContact.owner_id)
        .where(HiddenContact.fingerprint.in_(list(fingerprints)))
        .distinct()
    )
    return list(rows)
