import uuid
from collections.abc import Collection
from datetime import datetime

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import AuthSession, UserAccount
from src.identity import IdentityKind, fingerprint_sql


async def get_user_by_google_sub(session: AsyncSession, google_sub: str) -> UserAccount | None:
    return await session.scalar(select(UserAccount).where(UserAccount.google_sub == google_sub))


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> UserAccount | None:
    return await session.get(UserAccount, user_id)


async def get_user_by_college_email(session: AsyncSession, email: str) -> UserAccount | None:
    return await session.scalar(select(UserAccount).where(UserAccount.college_email == email))


async def get_user_by_email(session: AsyncSession, email: str) -> UserAccount | None:
    return await session.scalar(select(UserAccount).where(UserAccount.email == email))


async def get_users(session: AsyncSession, user_ids: list[uuid.UUID]) -> list[UserAccount]:
    return list(await session.scalars(select(UserAccount).where(UserAccount.id.in_(user_ids))))


async def ids_with_email_fingerprints(
    session: AsyncSession, fingerprints: Collection[str]
) -> list[uuid.UUID]:
    """Accounts whose sign-in or college email has one of these fingerprints."""
    fps = list(fingerprints)
    rows = await session.scalars(
        select(UserAccount.id).where(
            or_(
                fingerprint_sql(IdentityKind.EMAIL, UserAccount.email).in_(fps),
                fingerprint_sql(IdentityKind.EMAIL, UserAccount.college_email).in_(fps),
            )
        )
    )
    return list(rows)


async def add(session: AsyncSession, row: UserAccount | AuthSession) -> None:
    session.add(row)
    await session.flush()


async def get_user_for_token(
    session: AsyncSession, token_hash: str, now: datetime
) -> UserAccount | None:
    return await session.scalar(
        select(UserAccount)
        .join(AuthSession, AuthSession.user_id == UserAccount.id)
        .where(AuthSession.token_hash == token_hash, AuthSession.expires_at > now)
    )


async def delete_session(session: AsyncSession, token_hash: str) -> None:
    await session.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash))
