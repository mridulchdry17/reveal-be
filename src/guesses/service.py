"""Guessing someone's cards: one try per card, only on people you can see right now.

You can see someone while they're in your drop tonight, while their like waits for you,
or while you're matched. Anyone else's card, and your own, looks missing (404). The
guesses themselves are profile data (profiles.service), because they decide what
public_profiles shows: the answer of a card you've guessed, and how blurred a photo is.
"""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.schemas import Me
from src.drops import service as drop_service
from src.guesses.schemas import GuessResult
from src.matches import service as match_service
from src.profiles import service as profile_service
from src.profiles.exceptions import GuessCardNotFound


async def guess(
    session: AsyncSession, user: Me, card_id: uuid.UUID, pick: int, now: datetime
) -> GuessResult:
    owner_id = await profile_service.guess_card_owner(session, card_id)
    if (
        owner_id is None
        or owner_id == user.id
        or not await _can_see(session, user.id, owner_id, now)
    ):
        raise GuessCardNotFound
    answer = await profile_service.record_guess(session, user.id, card_id, pick)
    await session.commit()
    return GuessResult(correct=pick == answer, answer=answer, picked=pick)


async def _can_see(
    session: AsyncSession, viewer_id: uuid.UUID, owner_id: uuid.UUID, now: datetime
) -> bool:
    return await drop_service.in_tonight(
        session, viewer_id, owner_id, now
    ) or await match_service.can_see(session, viewer_id, owner_id)
