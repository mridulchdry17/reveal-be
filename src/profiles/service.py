import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import service as auth_service
from src.auth.schemas import Me
from src.profiles import constants as c
from src.profiles import repository
from src.profiles.exceptions import ProfileIncomplete, PromptNotFound
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
    PublicProfile,
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
    return await _save(session, user, profile)


async def update_preferences(session: AsyncSession, user: Me, body: PreferencesUpdate) -> MyProfile:
    profile = await _get_or_create(session, user)
    profile.gender = body.gender
    profile.interested_in = body.interested_in
    profile.match_on = list(body.match_on)
    return await _save(session, user, profile)


async def drop_candidates(
    session: AsyncSession, viewer_id: uuid.UUID, exclude: Sequence[uuid.UUID], limit: int
) -> list[uuid.UUID]:
    """People who could appear in this viewer's drop, best fit first.

    Both sides must want each other: their gender is in my "Interested in" and mine is in
    theirs. "Match me on" only ranks people higher; it never hides anyone. A complete
    profile implies a verified student, since only verified students can save one.
    """
    me = await repository.get_for_user(session, viewer_id)
    if me is None or me.completed_at is None or not me.gender or not me.interested_in:
        raise ProfileIncomplete("Finish your profile first")
    boosts = set(me.match_on)
    audience = repository.Audience(
        viewer_user_id=viewer_id,
        genders=[str(g) for g in c.WANTS[c.InterestedIn(me.interested_in)]],
        interested_in=[str(i) for i in c.WANTED_BY[c.Gender(me.gender)]],
        exclude=exclude,
        shared_interests=me.interests if c.MatchOn.SHARED_INTERESTS in boosts else (),
        hometown=me.hometown if c.MatchOn.SAME_HOMETOWN in boosts else None,
        vibe=me.vibe if c.MatchOn.SAME_VIBE in boosts else None,
        year=me.year if c.MatchOn.NEARBY_YEARS in boosts else None,
    )
    return await repository.candidates(session, audience, limit)


async def public_profiles(
    session: AsyncSession, viewer_id: uuid.UUID, owner_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, PublicProfile]:
    """What this viewer may see of each owner. The one place that decides visibility.

    Everyone has the same layout (constants.SHOWN_CARDS); swaps will open more per
    pair, which is why the viewer is passed in. Incomplete profiles are left out.
    """
    profiles = [p for p in await repository.get_for_users(session, owner_ids) if p.completed_at]
    if not profiles:
        return {}
    names = await auth_service.accounts(session, [p.user_id for p in profiles])
    prompts: dict[uuid.UUID, list[ProfilePrompt]] = {}
    for prompt in await repository.prompts_for(session, [p.id for p in profiles]):
        prompts.setdefault(prompt.profile_id, []).append(prompt)
    return {
        p.user_id: _to_public(p, names[p.user_id].name, prompts.get(p.id, []))
        for p in profiles
        if p.user_id in names
    }


async def prompt_of(session: AsyncSession, owner_id: uuid.UUID, prompt_id: uuid.UUID) -> PromptOut:
    """One of the owner's current prompts, e.g. the one someone is liking."""
    profile = await repository.get_for_user(session, owner_id)
    prompt = await repository.get_prompt(session, profile.id, prompt_id) if profile else None
    if prompt is None:
        raise PromptNotFound("That prompt isn't on their profile any more")
    return PromptOut(id=prompt.id, question=prompt.question, answer=prompt.answer)


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
        match_on=[],
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
        gender=c.Gender(p.gender) if p and p.gender else None,
        interested_in=c.InterestedIn(p.interested_in) if p and p.interested_in else None,
        match_on=[c.MatchOn(x) for x in p.match_on] if p else [],
        basics_done=basics_done,
        prompts_done=prompts_done,
        cards_done=cards_done,
        preferences_done=preferences_done,
        complete=basics_done and prompts_done and cards_done and preferences_done,
    )


def _to_public(p: Profile, full_name: str, prompts: list[ProfilePrompt]) -> PublicProfile:
    shown = [card for card in c.PUBLIC_CARDS if card in c.SHOWN_CARDS]
    return PublicProfile(
        nickname=p.nickname or "",
        vibe=p.vibe or "",
        interests=list(p.interests),
        prompts=[PromptOut(id=x.id, question=x.question, answer=x.answer) for x in prompts],
        first_name=first_name(full_name) if c.Card.FIRST_NAME in shown else None,
        branch=p.branch if c.Card.BRANCH in shown else None,
        year=p.year if c.Card.BRANCH in shown else None,
        hometown=p.hometown if c.Card.HOMETOWN in shown else None,
        looking_for=(
            c.LookingFor(p.looking_for) if c.Card.LOOKING_FOR in shown and p.looking_for else None
        ),
        shown_cards=shown,
        hidden_cards=[card for card in c.PUBLIC_CARDS if card not in shown],
    )
