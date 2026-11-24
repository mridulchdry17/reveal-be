"""Swaps: two matched people open a hidden card each, at the same moment.

Rules (CLAUDE.md, product rules 2-5):
- A card opens only when both have said yes, for both, in one transaction.
- Voice, photo and contact need both people to have one. Voice isn't offered otherwise.
- Photo needs at least one card swap first; contact needs the photo swap.
- Photo pieces: 1 per card swap up to 6, all 9 with the photo swap, and only while both
  have a photo, so nobody sees pieces of someone who can't see theirs.
- Everything is read through live matches, so unmatch, block and report close it all.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.schemas import Me
from src.matches import service as match_service
from src.matches.schemas import MatchInfo
from src.profiles import service as profile_service
from src.profiles.constants import Card
from src.profiles.schemas import OwnedCards
from src.swaps import repository
from src.swaps.constants import (
    CARD_SWAPS,
    NEEDS_BOTH,
    PHOTO_PIECES,
    PIECE_ORDER,
    PIECES_BEFORE_PHOTO_SWAP,
    SWAPPABLE,
    CardState,
    SwapStatus,
)
from src.swaps.exceptions import SwapNotAllowed, SwapNotFound
from src.swaps.models import Swap
from src.swaps.schemas import CardSwap, SwapBoard


@dataclass
class _Pair:
    """Everything the rules look at for one match, from the viewer's side."""

    viewer_id: uuid.UUID
    mine: OwnedCards
    theirs: OwnedCards
    accepted: set[Card] = field(default_factory=set)
    pending: dict[Card, Swap] = field(default_factory=dict)


async def opened_cards(
    session: AsyncSession, matches: Sequence[MatchInfo]
) -> dict[uuid.UUID, set[Card]]:
    """Cards each pair has swapped, keyed by the other person. Pass live matches only."""
    swaps = await repository.open_swaps(session, [m.id for m in matches]) if matches else []
    by_match: dict[uuid.UUID, set[Card]] = {}
    for s in swaps:
        if s.status == SwapStatus.ACCEPTED:
            by_match.setdefault(s.match_id, set()).add(Card(s.card))
    return {m.other_user_id: by_match.get(m.id, set()) for m in matches}


async def board(session: AsyncSession, viewer_id: uuid.UUID, match: MatchInfo) -> SwapBoard:
    return _board(await _pair(session, viewer_id, match))


async def propose(
    session: AsyncSession, user: Me, match_id: uuid.UUID, card: Card, now: datetime
) -> SwapBoard:
    """Ask to swap a card. If they already asked for the same one, this says yes."""
    match = await match_service.live_match(session, user.id, match_id)
    await repository.lock_match(session, match.id)
    pair = await _pair(session, user.id, match)
    state = _state(pair, card)
    if state == CardState.THEY_ASKED:
        _accept(pair.pending[card], now)
    elif state == CardState.CAN_ASK:
        swap = Swap(match_id=match.id, card=card, proposed_by_id=user.id, status=SwapStatus.PENDING)
        try:
            await repository.add(session, swap)
        except IntegrityError as error:  # the advisory lock makes this a bug, not a race
            raise SwapNotAllowed("That card can't be swapped right now") from error
    else:
        raise SwapNotAllowed("That card can't be swapped right now")
    await session.commit()
    return await board(session, user.id, match)


async def accept(
    session: AsyncSession, user: Me, match_id: uuid.UUID, card: Card, now: datetime
) -> SwapBoard:
    """Say yes to their request: the card opens for both of us now."""
    match = await match_service.live_match(session, user.id, match_id)
    await repository.lock_match(session, match.id)
    pair = await _pair(session, user.id, match)
    if _state(pair, card) != CardState.THEY_ASKED:
        raise SwapNotFound("They haven't asked to swap that card")
    if _blocked(pair, card) is not None:
        # Asked earlier, but since then one of them removed the card (or never had it).
        raise SwapNotAllowed("That card can't be swapped right now")
    _accept(pair.pending[card], now)
    await session.commit()
    return await board(session, user.id, match)


async def decline(
    session: AsyncSession, user: Me, match_id: uuid.UUID, card: Card, now: datetime
) -> SwapBoard:
    """Not yet. Nothing opens; either of us can ask again later."""
    match = await match_service.live_match(session, user.id, match_id)
    await repository.lock_match(session, match.id)
    pair = await _pair(session, user.id, match)
    if _state(pair, card) != CardState.THEY_ASKED:
        raise SwapNotFound("They haven't asked to swap that card")
    swap = pair.pending[card]
    swap.status = SwapStatus.DECLINED
    swap.decided_at = now
    await session.commit()
    return await board(session, user.id, match)


def _accept(swap: Swap, now: datetime) -> None:
    swap.status = SwapStatus.ACCEPTED
    swap.decided_at = now


async def _pair(session: AsyncSession, viewer_id: uuid.UUID, match: MatchInfo) -> _Pair:
    owned = await profile_service.owned_cards(session, [viewer_id, match.other_user_id])
    pair = _Pair(viewer_id=viewer_id, mine=owned[viewer_id], theirs=owned[match.other_user_id])
    for s in await repository.open_swaps(session, [match.id]):
        if s.status == SwapStatus.ACCEPTED:
            pair.accepted.add(Card(s.card))
        else:
            pair.pending[Card(s.card)] = s
    return pair


def _blocked(pair: _Pair, card: Card) -> CardState | None:
    """Why this card can't open yet, ignoring any request already made."""
    if card in NEEDS_BOTH:
        attr = str(card)
        if not getattr(pair.mine, attr):
            return CardState.NEEDS_YOURS
        if not getattr(pair.theirs, attr):
            return CardState.NEEDS_THEIRS
    if card == Card.PHOTO and not pair.accepted.intersection(CARD_SWAPS):
        return CardState.LOCKED
    if card == Card.CONTACT and Card.PHOTO not in pair.accepted:
        return CardState.LOCKED
    return None


def _state(pair: _Pair, card: Card) -> CardState:
    if card in pair.accepted:
        return CardState.OPEN
    if card in pair.pending:
        mine = pair.pending[card].proposed_by_id == pair.viewer_id
        return CardState.YOU_ASKED if mine else CardState.THEY_ASKED
    return _blocked(pair, card) or CardState.CAN_ASK


def _board(pair: _Pair) -> SwapBoard:
    voice_for_both = pair.mine.voice and pair.theirs.voice
    cards = [
        CardSwap(card=card, state=_state(pair, card))
        for card in SWAPPABLE
        if card != Card.VOICE or voice_for_both or Card.VOICE in pair.accepted
    ]
    return SwapBoard(cards=cards, photo_pieces=_pieces(pair))


def _pieces(pair: _Pair) -> list[int]:
    if not (pair.mine.photo and pair.theirs.photo):
        return []
    if Card.PHOTO in pair.accepted:
        return sorted(PIECE_ORDER[:PHOTO_PIECES])
    swapped = len(pair.accepted.intersection(CARD_SWAPS))
    return sorted(PIECE_ORDER[: min(swapped, PIECES_BEFORE_PHOTO_SWAP)])
