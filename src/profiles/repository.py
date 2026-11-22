import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Integer, case, delete, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.profiles.models import Profile, ProfilePrompt


async def get_for_user(session: AsyncSession, user_id: uuid.UUID) -> Profile | None:
    return await session.scalar(select(Profile).where(Profile.user_id == user_id))


async def get_for_users(session: AsyncSession, user_ids: Sequence[uuid.UUID]) -> list[Profile]:
    rows = await session.scalars(select(Profile).where(Profile.user_id.in_(user_ids)))
    return list(rows)


async def prompts_for(
    session: AsyncSession, profile_ids: Sequence[uuid.UUID]
) -> list[ProfilePrompt]:
    rows = await session.scalars(
        select(ProfilePrompt)
        .where(ProfilePrompt.profile_id.in_(profile_ids))
        .order_by(ProfilePrompt.position)
    )
    return list(rows)


async def get_prompt(
    session: AsyncSession, profile_id: uuid.UUID, prompt_id: uuid.UUID
) -> ProfilePrompt | None:
    return await session.scalar(
        select(ProfilePrompt).where(
            ProfilePrompt.id == prompt_id, ProfilePrompt.profile_id == profile_id
        )
    )


@dataclass(frozen=True)
class Audience:
    """Who a viewer may see, already decided by the service. Each boost adds 1 to the fit."""

    viewer_user_id: uuid.UUID
    genders: Sequence[str]
    interested_in: Sequence[str]
    exclude: Sequence[uuid.UUID]
    shared_interests: Sequence[str] = ()
    hometown: str | None = None
    vibe: str | None = None
    year: int | None = None


async def candidates(session: AsyncSession, audience: Audience, limit: int) -> list[uuid.UUID]:
    """Complete profiles that fit the audience, best fit first, ties in random order."""
    a = audience
    fit: list[ColumnElement[int]] = []
    if a.shared_interests:
        fit.append(case((Profile.interests.overlap(list(a.shared_interests)), 1), else_=0))
    if a.hometown:
        fit.append(case((func.lower(Profile.hometown) == a.hometown.lower(), 1), else_=0))
    if a.vibe:
        fit.append(case((Profile.vibe == a.vibe, 1), else_=0))
    if a.year is not None:
        fit.append(case((func.abs(Profile.year - a.year) <= 1, 1), else_=0))
    score = sum(fit[1:], fit[0]) if fit else literal(0, Integer)
    query = (
        select(Profile.user_id)
        .where(
            Profile.completed_at.is_not(None),
            Profile.user_id != a.viewer_user_id,
            Profile.gender.in_(a.genders),
            Profile.interested_in.in_(a.interested_in),
        )
        .order_by(score.desc(), func.random())
        .limit(limit)
    )
    if a.exclude:
        query = query.where(Profile.user_id.not_in(a.exclude))
    return list(await session.scalars(query))


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
