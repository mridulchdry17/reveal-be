import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Integer, and_, case, delete, exists, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.identity import fingerprint_sql
from src.profiles.models import Guess, GuessCard, GuessHint, Profile, ProfilePrompt

# Finished once (completed_at) and has guess cards: profiles finished before guess cards
# existed count as unfinished until their owner adds them.
_COMPLETE = and_(
    Profile.completed_at.is_not(None),
    exists().where(GuessCard.profile_id == Profile.id),
)


async def get_for_user(session: AsyncSession, user_id: uuid.UUID) -> Profile | None:
    return await session.scalar(select(Profile).where(Profile.user_id == user_id))


async def get_for_users(session: AsyncSession, user_ids: Sequence[uuid.UUID]) -> list[Profile]:
    rows = await session.scalars(select(Profile).where(Profile.user_id.in_(user_ids)))
    return list(rows)


async def complete_for_users(session: AsyncSession, user_ids: Sequence[uuid.UUID]) -> list[Profile]:
    rows = await session.scalars(select(Profile).where(Profile.user_id.in_(user_ids), _COMPLETE))
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
            _COMPLETE,
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


async def ids_with_contact_fingerprints(
    session: AsyncSession, fingerprints: Collection[str]
) -> list[uuid.UUID]:
    """Owners whose card-7 contact (phone or Instagram) has one of these fingerprints."""
    rows = await session.scalars(
        select(Profile.user_id).where(
            Profile.contact_value.is_not(None),
            fingerprint_sql(Profile.contact_kind, Profile.contact_value).in_(list(fingerprints)),
        )
    )
    return list(rows)


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


async def guess_cards_for(
    session: AsyncSession, profile_ids: Sequence[uuid.UUID]
) -> list[GuessCard]:
    rows = await session.scalars(
        select(GuessCard).where(GuessCard.profile_id.in_(profile_ids)).order_by(GuessCard.position)
    )
    return list(rows)


async def replace_guess_cards(
    session: AsyncSession, profile_id: uuid.UUID, keep: Sequence[uuid.UUID], new: list[GuessCard]
) -> None:
    """Delete every card of this profile not in `keep` (their guesses go too), add `new`."""
    await session.execute(
        delete(GuessCard).where(GuessCard.profile_id == profile_id, GuessCard.id.not_in(keep))
    )
    session.add_all(new)
    await session.flush()


async def guess_card_with_owner(
    session: AsyncSession, card_id: uuid.UUID
) -> tuple[GuessCard, uuid.UUID] | None:
    row = (
        await session.execute(
            select(GuessCard, Profile.user_id)
            .join(Profile, Profile.id == GuessCard.profile_id)
            .where(GuessCard.id == card_id)
        )
    ).first()
    return (row[0], row[1]) if row else None


async def guesses_by(
    session: AsyncSession, guesser_id: uuid.UUID, card_ids: Sequence[uuid.UUID]
) -> list[Guess]:
    rows = await session.scalars(
        select(Guess).where(Guess.guesser_id == guesser_id, Guess.card_id.in_(card_ids))
    )
    return list(rows)


async def get_guess(
    session: AsyncSession, guesser_id: uuid.UUID, card_id: uuid.UUID
) -> Guess | None:
    return await session.scalar(
        select(Guess).where(Guess.guesser_id == guesser_id, Guess.card_id == card_id)
    )


async def right_guess_counts(
    session: AsyncSession, guesser_id: uuid.UUID, owner_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """Right guesses by this guesser on each owner's current cards."""
    rows = await session.execute(
        select(Profile.user_id, func.count(Guess.id))
        .join(GuessCard, GuessCard.profile_id == Profile.id)
        .join(Guess, Guess.card_id == GuessCard.id)
        .where(Profile.user_id.in_(owner_ids), Guess.guesser_id == guesser_id, Guess.correct)
        .group_by(Profile.user_id)
    )
    return {user_id: count for user_id, count in rows}


async def right_guess_counts_on(
    session: AsyncSession, owner_id: uuid.UUID, guesser_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """Right guesses on this owner's current cards, per guesser."""
    rows = await session.execute(
        select(Guess.guesser_id, func.count(Guess.id))
        .join(GuessCard, Guess.card_id == GuessCard.id)
        .join(Profile, Profile.id == GuessCard.profile_id)
        .where(Profile.user_id == owner_id, Guess.guesser_id.in_(guesser_ids), Guess.correct)
        .group_by(Guess.guesser_id)
    )
    return {guesser_id: count for guesser_id, count in rows}


async def guess_stats(
    session: AsyncSession, card_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, int]]:
    """Per card: how many people guessed it, and how many got it right."""
    rows = await session.execute(
        select(Guess.card_id, func.count(Guess.id), func.count(Guess.id).filter(Guess.correct))
        .where(Guess.card_id.in_(card_ids))
        .group_by(Guess.card_id)
    )
    return {card_id: (guessed, right) for card_id, guessed, right in rows}


async def add_guess(session: AsyncSession, guess: Guess) -> None:
    session.add(guess)
    await session.flush()


async def add(session: AsyncSession, row: Profile) -> None:
    session.add(row)
    await session.flush()


async def hint_on(
    session: AsyncSession, user_id: uuid.UUID, card_id: uuid.UUID
) -> GuessHint | None:
    return await session.scalar(
        select(GuessHint).where(GuessHint.user_id == user_id, GuessHint.card_id == card_id)
    )


async def hint_in(session: AsyncSession, user_id: uuid.UUID, drop_date: date) -> GuessHint | None:
    return await session.scalar(
        select(GuessHint).where(GuessHint.user_id == user_id, GuessHint.drop_date == drop_date)
    )


async def hints_by(
    session: AsyncSession, user_id: uuid.UUID, card_ids: Sequence[uuid.UUID]
) -> list[GuessHint]:
    rows = await session.scalars(
        select(GuessHint).where(GuessHint.user_id == user_id, GuessHint.card_id.in_(card_ids))
    )
    return list(rows)


async def add_hint(session: AsyncSession, hint: GuessHint) -> None:
    session.add(hint)
    await session.flush()
