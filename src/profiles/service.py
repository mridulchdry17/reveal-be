from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.schemas import Me
from src.profiles import constants as c
from src.profiles import repository
from src.profiles.models import Profile, ProfilePrompt
from src.profiles.schemas import (
    BasicsUpdate,
    CardsUpdate,
    MyProfile,
    Option,
    PreferencesUpdate,
    ProfileOptions,
    PromptOut,
    PromptsUpdate,
)


def options() -> ProfileOptions:
    return ProfileOptions(
        vibes=c.VIBES,
        interest_suggestions=c.INTEREST_SUGGESTIONS,
        min_interests=c.MIN_INTERESTS,
        max_interests=c.MAX_INTERESTS,
        prompt_questions=c.PROMPT_QUESTIONS,
        prompt_answer_max=c.PROMPT_ANSWER_MAX,
        nickname_suggestions=c.NICKNAME_SUGGESTIONS,
        looking_for=[Option(value=k, label=v) for k, v in c.LOOKING_FOR_LABELS.items()],
    )


async def my_profile(session: AsyncSession, user: Me) -> MyProfile:
    profile = await repository.get_for_user(session, user.id)
    if profile is None:
        return _to_mine(user, None, [])
    return _to_mine(user, profile, await repository.prompts(session, profile.id))


async def update_basics(session: AsyncSession, user: Me, body: BasicsUpdate) -> MyProfile:
    profile = await _get_or_create(session, user)
    profile.nickname = body.nickname
    profile.vibe = body.vibe
    profile.interests = body.interests
    return await _save(session, user, profile)


async def update_prompts(session: AsyncSession, user: Me, body: PromptsUpdate) -> MyProfile:
    profile = await _get_or_create(session, user)
    await repository.replace_prompts(
        session, profile.id, [(p.question, p.answer) for p in body.prompts]
    )
    return await _save(session, user, profile)


async def update_cards(session: AsyncSession, user: Me, body: CardsUpdate) -> MyProfile:
    profile = await _get_or_create(session, user)
    profile.branch = body.branch
    profile.year = body.year
    profile.hometown = body.hometown
    profile.looking_for = body.looking_for
    profile.shown_cards = list(body.shown_cards)
    return await _save(session, user, profile)


async def update_preferences(session: AsyncSession, user: Me, body: PreferencesUpdate) -> MyProfile:
    profile = await _get_or_create(session, user)
    profile.gender = body.gender
    profile.interested_in = body.interested_in
    profile.match_on = list(body.match_on)
    # "Women write first" is a choice for women only; ignore it for anyone else.
    profile.women_write_first = body.women_write_first and body.gender == c.Gender.WOMAN
    return await _save(session, user, profile)


def first_name(full_name: str) -> str:
    """Card 1. The first word of the Google account name."""
    return full_name.split()[0] if full_name.strip() else ""


async def _get_or_create(session: AsyncSession, user: Me) -> Profile:
    profile = await repository.get_for_user(session, user.id)
    if profile is not None:
        return profile
    profile = Profile(
        user_id=user.id,
        interests=[],
        shown_cards=[str(card) for card in c.DEFAULT_SHOWN],
        match_on=[],
        women_write_first=False,
    )
    try:
        async with session.begin_nested():
            await repository.add(session, profile)
    except IntegrityError:
        # Two screens saved at the same moment and the other one created it.
        existing = await repository.get_for_user(session, user.id)
        if existing is None:
            raise
        return existing
    return profile


async def _save(session: AsyncSession, user: Me, profile: Profile) -> MyProfile:
    prompts = await repository.prompts(session, profile.id)
    mine = _to_mine(user, profile, prompts)
    if mine.complete and profile.completed_at is None:
        profile.completed_at = datetime.now(UTC)
    await session.commit()
    return mine


def _to_mine(user: Me, profile: Profile | None, prompts: list[ProfilePrompt]) -> MyProfile:
    p = profile
    basics_done = bool(p and p.nickname and p.vibe and len(p.interests) >= c.MIN_INTERESTS)
    prompts_done = len(prompts) == c.PROMPT_COUNT
    cards_done = bool(p and p.branch and p.year and p.hometown and p.looking_for)
    preferences_done = bool(p and p.gender and p.interested_in)
    return MyProfile(
        first_name=first_name(user.name),
        nickname=p.nickname if p else None,
        vibe=p.vibe if p else None,
        interests=list(p.interests) if p else [],
        prompts=[PromptOut(id=x.id, question=x.question, answer=x.answer) for x in prompts],
        branch=p.branch if p else None,
        year=p.year if p else None,
        hometown=p.hometown if p else None,
        looking_for=c.LookingFor(p.looking_for) if p and p.looking_for else None,
        shown_cards=[c.Card(x) for x in p.shown_cards] if p else list(c.DEFAULT_SHOWN),
        gender=c.Gender(p.gender) if p and p.gender else None,
        interested_in=c.InterestedIn(p.interested_in) if p and p.interested_in else None,
        match_on=[c.MatchOn(x) for x in p.match_on] if p else [],
        women_write_first=p.women_write_first if p else False,
        basics_done=basics_done,
        prompts_done=prompts_done,
        cards_done=cards_done,
        preferences_done=preferences_done,
        complete=basics_done and prompts_done and cards_done and preferences_done,
    )
