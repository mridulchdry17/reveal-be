import uuid
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import AuthSession, UserAccount


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
