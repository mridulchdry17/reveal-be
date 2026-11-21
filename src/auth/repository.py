from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import AuthSession, UserAccount


async def get_user_by_google_sub(session: AsyncSession, google_sub: str) -> UserAccount | None:
    return await session.scalar(select(UserAccount).where(UserAccount.google_sub == google_sub))


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
