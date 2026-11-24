import secrets
import uuid
from collections.abc import Collection, Mapping, Sequence
from datetime import UTC, datetime

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src import media
from src.auth import service as auth_service
from src.auth.schemas import Me
from src.config import settings
from src.profiles import constants as c
from src.profiles import photo, repository, voice
from src.profiles.exceptions import (
    AlreadyGuessed,
    GuessCardNotFound,
    NotAPhoto,
    NotAVoiceNote,
    PhotoNotFound,
    PhotoTooLarge,
    ProfileIncomplete,
    PromptNotFound,
    VoiceNoteNotFound,
    VoiceNoteTooLarge,
)
from src.profiles.models import Guess, GuessCard, Profile, ProfilePrompt
from src.profiles.schemas import (
    BasicsUpdate,
    CardsUpdate,
    Contact,
    GuessCardOut,
    GuessCardsUpdate,
    MyGuessCard,
    MyProfile,
    Option,
    OwnedCards,
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
        guess_kinds=[Option(value=k, label=v) for k, v in c.GUESS_KIND_LABELS.items()],
        guess_suggestions=c.GUESS_SUGGESTIONS,
        guess_question_max=c.GUESS_QUESTION_MAX,
        guess_option_max=c.GUESS_OPTION_MAX,
    )


async def my_profile(session: AsyncSession, user: Me) -> MyProfile:
    profile = await repository.get_for_user(session, user.id)
    if profile is None:
        return _to_mine(user, None, [], [])
    return _to_mine(
        user,
        profile,
        await repository.prompts(session, profile.id),
        await repository.guess_cards_for(session, [profile.id]),
    )


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


async def update_guesses(session: AsyncSession, user: Me, body: GuessCardsUpdate) -> MyProfile:
    """Replace all three guess cards. A card saved unchanged keeps its id and the guesses
    people made on it; a changed card is a new card, and guesses on the old one are gone."""
    profile = await _get_or_create(session, user)
    current = {g.position: g for g in await repository.guess_cards_for(session, [profile.id])}
    keep: list[uuid.UUID] = []
    new: list[GuessCard] = []
    for position, card in enumerate(body.cards):
        old = current.get(position)
        if old and (old.kind, old.question, list(old.options), old.answer) == (
            card.kind,
            card.question,
            card.options,
            card.answer,
        ):
            keep.append(old.id)
        else:
            new.append(
                GuessCard(
                    profile_id=profile.id,
                    position=position,
                    kind=card.kind,
                    question=card.question,
                    options=card.options,
                    answer=card.answer,
                )
            )
    await repository.replace_guess_cards(session, profile.id, keep, new)
    return await _save(session, user, profile)


async def update_cards(session: AsyncSession, user: Me, body: CardsUpdate) -> MyProfile:
    profile = await _get_or_create(session, user)
    profile.branch = body.branch
    profile.year = body.year
    profile.hometown = body.hometown
    profile.looking_for = body.looking_for
    return await _save(session, user, profile)


async def update_contact(session: AsyncSession, user: Me, body: Contact) -> MyProfile:
    profile = await _get_or_create(session, user)
    profile.contact_kind = body.kind
    profile.contact_value = body.value
    return await _save(session, user, profile)


async def remove_contact(session: AsyncSession, user: Me) -> MyProfile:
    profile = await _get_or_create(session, user)
    profile.contact_kind = None
    profile.contact_value = None
    return await _save(session, user, profile)


async def update_photo(session: AsyncSession, user: Me, data: bytes) -> MyProfile:
    """Card 6. Re-encoded and stored privately; the old photo is deleted once saved."""
    if len(data) > settings.profile_photo_max_bytes:
        raise PhotoTooLarge("That photo is too large")
    jpeg = await run_in_threadpool(photo.reencode, data)
    if jpeg is None:
        raise NotAPhoto("That file isn't a JPEG, PNG or WebP photo")
    profile = await _get_or_create(session, user)
    old_key = profile.photo_key
    key = f"photos/{user.id}/{secrets.token_hex(16)}.jpg"
    await media.put(key, jpeg, "image/jpeg")
    profile.photo_key = key
    mine = await _save(session, user, profile)
    if old_key:
        await media.delete(old_key)
    return mine


async def my_photo(session: AsyncSession, user: Me) -> bytes:
    """The owner's own photo. Nobody else gets it until a photo swap (part 4)."""
    profile = await repository.get_for_user(session, user.id)
    data = await media.get(profile.photo_key) if profile and profile.photo_key else None
    if data is None:
        raise PhotoNotFound("No photo yet")
    return data


async def remove_photo(session: AsyncSession, user: Me) -> MyProfile:
    profile = await _get_or_create(session, user)
    old_key = profile.photo_key
    profile.photo_key = None
    mine = await _save(session, user, profile)
    if old_key:
        await media.delete(old_key)
    return mine


async def update_voice(session: AsyncSession, user: Me, data: bytes, seconds: int) -> MyProfile:
    """Card 5, optional. Stored privately as recorded; the old note is deleted once saved."""
    if len(data) > settings.voice_note_max_bytes:
        raise VoiceNoteTooLarge("That voice note is too long")
    kind = voice.detect_audio_type(data)
    if kind is None:
        raise NotAVoiceNote("That file isn't a voice note")
    profile = await _get_or_create(session, user)
    old_key = profile.voice_key
    key = f"voice/{user.id}/{secrets.token_hex(16)}.{kind}"
    await media.put(key, data, voice.VOICE_TYPES[kind])
    profile.voice_key = key
    profile.voice_type = kind
    profile.voice_seconds = seconds
    mine = await _save(session, user, profile)
    if old_key:
        await media.delete(old_key)
    return mine


async def my_voice(session: AsyncSession, user: Me) -> tuple[bytes, str]:
    """The owner's own voice note and its MIME type. Others hear it only after a swap."""
    profile = await repository.get_for_user(session, user.id)
    if profile is None or not profile.voice_key or not profile.voice_type:
        raise VoiceNoteNotFound("No voice note yet")
    data = await media.get(profile.voice_key)
    if data is None:
        raise VoiceNoteNotFound("No voice note yet")
    return data, voice.VOICE_TYPES[profile.voice_type]


async def stored_photo(session: AsyncSession, owner_id: uuid.UUID) -> bytes | None:
    """The owner's photo file. Only swaps.service calls this, after checking the pair."""
    profile = await repository.get_for_user(session, owner_id)
    return await media.get(profile.photo_key) if profile and profile.photo_key else None


async def stored_voice(session: AsyncSession, owner_id: uuid.UUID) -> tuple[bytes, str] | None:
    """The owner's voice note and its MIME type. Only swaps.service calls this."""
    profile = await repository.get_for_user(session, owner_id)
    if profile is None or not profile.voice_key or not profile.voice_type:
        return None
    data = await media.get(profile.voice_key)
    return (data, voice.VOICE_TYPES[profile.voice_type]) if data is not None else None


async def remove_voice(session: AsyncSession, user: Me) -> MyProfile:
    profile = await _get_or_create(session, user)
    old_key = profile.voice_key
    profile.voice_key = None
    profile.voice_type = None
    profile.voice_seconds = None
    mine = await _save(session, user, profile)
    if old_key:
        await media.delete(old_key)
    return mine


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
    found = await repository.complete_for_users(session, [viewer_id])
    me = found[0] if found else None
    if me is None or not me.gender or not me.interested_in:
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
    session: AsyncSession,
    viewer_id: uuid.UUID,
    owner_ids: Sequence[uuid.UUID],
    opened: Mapping[uuid.UUID, Collection[c.Card]] | None = None,
) -> dict[uuid.UUID, PublicProfile]:
    """What this viewer may see of each owner. The one place that decides visibility.

    Everyone has the same layout (constants.SHOWN_CARDS). `opened` adds the cards a pair
    has swapped, per owner; only swaps.service works that out, from live matches, so an
    ended match opens nothing. Incomplete profiles are left out.

    Guess cards show their answer only to a viewer who has already guessed that card.
    """
    profiles = await repository.complete_for_users(session, owner_ids)
    if not profiles:
        return {}
    names = await auth_service.accounts(session, [p.user_id for p in profiles])
    profile_ids = [p.id for p in profiles]
    prompts: dict[uuid.UUID, list[ProfilePrompt]] = {}
    for prompt in await repository.prompts_for(session, profile_ids):
        prompts.setdefault(prompt.profile_id, []).append(prompt)
    cards: dict[uuid.UUID, list[GuessCard]] = {}
    all_cards = await repository.guess_cards_for(session, profile_ids)
    for card in all_cards:
        cards.setdefault(card.profile_id, []).append(card)
    picks = {
        g.card_id: g
        for g in await repository.guesses_by(session, viewer_id, [x.id for x in all_cards])
    }
    viewer = await repository.get_for_user(session, viewer_id)
    viewer_has_photo = bool(viewer and viewer.photo_key)
    return {
        p.user_id: _to_public(
            p,
            names[p.user_id].name,
            prompts.get(p.id, []),
            (opened or {}).get(p.user_id, ()),
            _guess_cards_out(cards.get(p.id, []), picks),
            viewer_has_photo,
        )
        for p in profiles
        if p.user_id in names
    }


async def guess_card_owner(session: AsyncSession, card_id: uuid.UUID) -> uuid.UUID | None:
    """Whose guess card this is, or None if there's no such card."""
    found = await repository.guess_card_with_owner(session, card_id)
    return found[1] if found else None


async def record_guess(
    session: AsyncSession, guesser_id: uuid.UUID, card_id: uuid.UUID, pick: int
) -> int:
    """Save someone's one try at a card and return the true option. Doesn't commit.

    guesses.service calls this only after checking the guesser may see the card's owner.
    """
    found = await repository.guess_card_with_owner(session, card_id)
    if found is None:
        raise GuessCardNotFound
    card, _ = found
    if await repository.get_guess(session, guesser_id, card_id):
        raise AlreadyGuessed("You've already guessed this one")
    guess = Guess(guesser_id=guesser_id, card_id=card_id, picked=pick, correct=pick == card.answer)
    try:
        async with session.begin_nested():
            await repository.add_guess(session, guess)
    except IntegrityError as error:  # the same guess sent twice at once
        raise AlreadyGuessed("You've already guessed this one") from error
    return card.answer


async def right_guesses(
    session: AsyncSession, viewer_id: uuid.UUID, owner_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """How many of each owner's current cards this viewer guessed right (0-3)."""
    counts = await repository.right_guess_counts(session, viewer_id, owner_ids)
    return {uid: counts.get(uid, 0) for uid in owner_ids}


async def blurred_photo(session: AsyncSession, viewer_id: uuid.UUID, owner_id: uuid.UUID) -> bytes:
    """The owner's photo, blurred past recognition; a little less per right guess.

    Only when both have a photo, so nobody sees even this much of someone who can't see
    theirs. drops.service and matches.service call it after checking the viewer may see
    the owner (in tonight's drop, or a like waiting for them).
    """
    found = {p.user_id: p for p in await repository.get_for_users(session, [viewer_id, owner_id])}
    viewer, owner = found.get(viewer_id), found.get(owner_id)
    data = None
    if viewer and viewer.photo_key and owner and owner.photo_key:
        data = await media.get(owner.photo_key)
    if data is None:
        raise PhotoNotFound("No photo to show")
    right = (await right_guesses(session, viewer_id, [owner_id]))[owner_id]
    tiny = c.BLUR_STEPS[min(right, len(c.BLUR_STEPS) - 1)]
    return await run_in_threadpool(photo.blurred, data, tiny, c.BLUR_SIDE)


async def owned_cards(
    session: AsyncSession, user_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, OwnedCards]:
    """Who has a voice note, photo and contact card. Missing profiles own nothing."""
    profiles = {p.user_id: p for p in await repository.get_for_users(session, user_ids)}
    return {
        uid: OwnedCards(
            voice=bool(p and p.voice_key),
            photo=bool(p and p.photo_key),
            contact=bool(p and p.contact_kind and p.contact_value),
        )
        for uid in user_ids
        for p in [profiles.get(uid)]
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
    guess_cards = await repository.guess_cards_for(session, [profile.id])
    mine = _to_mine(user, profile, prompts, guess_cards)
    if mine.complete and profile.completed_at is None:
        profile.completed_at = datetime.now(UTC)
    await session.commit()
    return mine


def _to_mine(
    user: Me, profile: Profile | None, prompts: list[ProfilePrompt], guess_cards: list[GuessCard]
) -> MyProfile:
    p = profile
    basics_done = bool(p and p.nickname and p.vibe and len(p.interests) >= c.MIN_INTERESTS)
    prompts_done = len(prompts) == c.PROMPT_COUNT
    guesses_done = len(guess_cards) == c.GUESS_CARD_COUNT
    cards_done = bool(p and p.branch and p.year and p.hometown and p.looking_for)
    preferences_done = bool(p and p.gender and p.interested_in)
    return MyProfile(
        first_name=first_name(user.name),
        nickname=p.nickname if p else None,
        vibe=p.vibe if p else None,
        interests=list(p.interests) if p else [],
        prompts=[PromptOut(id=x.id, question=x.question, answer=x.answer) for x in prompts],
        guess_cards=[
            MyGuessCard(
                id=g.id,
                kind=c.GuessKind(g.kind),
                question=g.question,
                options=list(g.options),
                answer=g.answer,
            )
            for g in guess_cards
        ],
        branch=p.branch if p else None,
        year=p.year if p else None,
        hometown=p.hometown if p else None,
        looking_for=c.LookingFor(p.looking_for) if p and p.looking_for else None,
        voice_seconds=p.voice_seconds if p and p.voice_key else None,
        has_photo=bool(p and p.photo_key),
        contact=(
            Contact.model_construct(kind=c.ContactKind(p.contact_kind), value=p.contact_value)
            if p and p.contact_kind and p.contact_value
            else None
        ),
        gender=c.Gender(p.gender) if p and p.gender else None,
        interested_in=c.InterestedIn(p.interested_in) if p and p.interested_in else None,
        match_on=[c.MatchOn(x) for x in p.match_on] if p else [],
        basics_done=basics_done,
        prompts_done=prompts_done,
        guesses_done=guesses_done,
        cards_done=cards_done,
        preferences_done=preferences_done,
        complete=basics_done and prompts_done and guesses_done and cards_done and preferences_done,
    )


def _guess_cards_out(
    cards: list[GuessCard], picks: Mapping[uuid.UUID, Guess]
) -> list[GuessCardOut]:
    """Their cards for one viewer: the answer only on cards this viewer has guessed."""
    return [
        GuessCardOut(
            id=g.id,
            kind=c.GuessKind(g.kind),
            question=g.question,
            options=list(g.options),
            picked=picks[g.id].picked if g.id in picks else None,
            answer=g.answer if g.id in picks else None,
        )
        for g in cards
    ]


def _to_public(
    p: Profile,
    full_name: str,
    prompts: list[ProfilePrompt],
    opened: Collection[c.Card],
    guess_cards: list[GuessCardOut],
    viewer_has_photo: bool,
) -> PublicProfile:
    cards = [card for card in c.PUBLIC_CARDS if card != c.Card.VOICE or p.voice_key]
    shown = [card for card in cards if card in c.SHOWN_CARDS or card in opened]
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
        voice_seconds=p.voice_seconds if c.Card.VOICE in shown and p.voice_key else None,
        contact=(
            Contact.model_construct(kind=c.ContactKind(p.contact_kind), value=p.contact_value)
            if c.Card.CONTACT in shown and p.contact_kind and p.contact_value
            else None
        ),
        shown_cards=shown,
        hidden_cards=[card for card in cards if card not in shown],
        guess_cards=guess_cards,
        right_guesses=sum(1 for g in guess_cards if g.answer is not None and g.picked == g.answer),
        has_blurred_photo=viewer_has_photo and bool(p.photo_key),
    )
