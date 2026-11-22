import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.profiles.models import Profile, ProfilePrompt


async def get_for_user(session: AsyncSession, user_id: uuid.UUID) -> Profile | None:
    return await session.scalar(select(Profile).where(Profile.user_id == user_id))


async def prompts(session: AsyncSession, profile_id: uuid.UUID) -> list[ProfilePrompt]:
    rows = await session.scalars(
        select(ProfilePrompt)
        .where(ProfilePrompt.profile_id == profile_id)
        .order_by(ProfilePrompt.position)
    )
    return list(rows)


async def replace_prompts(
    session: AsyncSession, profile_id: uuid.UUID, items: list[tuple[str, str]]
) -> None:
    await session.execute(delete(ProfilePrompt).where(ProfilePrompt.profile_id == profile_id))
    session.add_all(
        ProfilePrompt(profile_id=profile_id, position=i, question=q, answer=a)
        for i, (q, a) in enumerate(items)
    )
    await session.flush()


async def add(session: AsyncSession, row: Profile) -> None:
    session.add(row)
    await session.flush()
