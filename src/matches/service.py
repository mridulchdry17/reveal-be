"""Likes and matches. A like waits in the other person's Likes list; liking back matches."""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.schemas import Me
from src.hides import service as hide_service
from src.matches import repository
from src.matches.constants import LOOKS_PENDING, LikedKind, LikeStatus
from src.matches.exceptions import AlreadyLiked, LikeAlreadyAnswered, LikeNotFound, MatchNotFound
from src.matches.models import Like, Match
from src.matches.schemas import Liked, MatchInfo, MatchResult, ReceivedLike, SentLike
from src.notifications import service as notification_service
from src.notifications.constants import Event
from src.profiles import service as profile_service
from src.profiles.constants import GuessKind


async def send_like(
    session: AsyncSession,
    from_user_id: uuid.UUID,
    to_user_id: uuid.UUID,
    liked: Liked,
    comment: str | None,
    now: datetime,
) -> uuid.UUID | None:
    """Like a prompt or guess card. Returns the new match's id if it's a match. Doesn't
    commit: the caller does.

    If they had already liked me, this is a match straight away. If they had passed on me,
    my like is quietly filed as passed so it never reaches them again.
    """
    if await repository.get_like(session, from_user_id, to_user_id):
        raise AlreadyLiked("You've already liked them")
    theirs = await repository.get_like(session, to_user_id, from_user_id)
    status = LikeStatus.PENDING
    if theirs and theirs.status == LikeStatus.PASSED:
        status = LikeStatus.PASSED
    elif theirs and theirs.status == LikeStatus.PENDING:
        status = LikeStatus.MATCHED
        theirs.status = LikeStatus.MATCHED
        theirs.decided_at = now
    await repository.add_like(
        session,
        Like(
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            kind=liked.kind,
            question=liked.question,
            answer=liked.answer,
            guess_kind=liked.guess_kind,
            comment=comment,
            status=status,
            decided_at=now if status != LikeStatus.PENDING else None,
        ),
    )
    if status == LikeStatus.MATCHED:
        match_id = await repository.add_match(session, *sorted((from_user_id, to_user_id)))
        await notification_service.notify(session, to_user_id, Event.MATCH, "/app/chats")
        return match_id
    if status == LikeStatus.PENDING:
        await notification_service.notify(session, to_user_id, Event.LIKE, "/app/likes")
    return None


async def live_matches(session: AsyncSession, user_id: uuid.UUID) -> list[MatchInfo]:
    return [_info(m, user_id) for m in await repository.live_matches(session, user_id)]


async def live_match(session: AsyncSession, user_id: uuid.UUID, match_id: uuid.UUID) -> MatchInfo:
    """One of my live matches, or MatchNotFound. Every chat and safety action starts here."""
    match = await repository.live_match(session, user_id, match_id)
    if match is None:
        raise MatchNotFound
    return _info(match, user_id)


async def end(
    session: AsyncSession, user_id: uuid.UUID, match_id: uuid.UUID, now: datetime
) -> MatchInfo:
    """End a match for both people. Doesn't commit: block and report end it in their own
    transaction. Everything swapped closes with it: swaps are only read for live matches."""
    match = await repository.live_match(session, user_id, match_id)
    if match is None:
        raise MatchNotFound
    match.ended_at = now
    match.ended_by_id = user_id
    return _info(match, user_id)


async def unmatch(session: AsyncSession, user: Me, match_id: uuid.UUID, now: datetime) -> None:
    await end(session, user.id, match_id, now)
    await session.commit()


def _info(match: Match, user_id: uuid.UUID) -> MatchInfo:
    other = match.user_b_id if match.user_a_id == user_id else match.user_a_id
    return MatchInfo(id=match.id, other_user_id=other, matched_at=match.created_at)


async def can_see(session: AsyncSession, viewer_id: uuid.UUID, owner_id: uuid.UUID) -> bool:
    """The owner liked the viewer and is waiting for an answer, or they're matched now."""
    like = await repository.get_like(session, owner_id, viewer_id)
    if like is not None and like.status == LikeStatus.PENDING:
        return not await hide_service.is_hidden(session, viewer_id, owner_id)
    return await repository.live_match_between(session, viewer_id, owner_id) is not None


async def blurred_photo(session: AsyncSession, user: Me, like_id: uuid.UUID) -> bytes:
    """The blurred photo of someone whose like is waiting for me."""
    like = await repository.get_like_by_id(session, like_id)
    if like is None or like.to_user_id != user.id or like.status != LikeStatus.PENDING:
        raise LikeNotFound
    if await hide_service.is_hidden(session, user.id, like.from_user_id):
        raise LikeNotFound
    return await profile_service.blurred_photo(session, user.id, like.from_user_id)


async def connected_ids(session: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    """People this user already has history with, so the drop doesn't show them again."""
    return await repository.connected_ids(session, user_id)


async def received_likes(session: AsyncSession, user: Me) -> list[ReceivedLike]:
    hidden = await hide_service.hidden_ids(session, user.id)
    likes = [
        like
        for like in await repository.likes_to(session, user.id, LikeStatus.PENDING)
        if like.from_user_id not in hidden
    ]
    profiles = await profile_service.public_profiles(
        session, user.id, [like.from_user_id for like in likes]
    )
    return [
        ReceivedLike(
            id=like.id,
            liked=_liked(like),
            prompt_question=like.question,
            prompt_answer=like.answer,
            comment=like.comment,
            created_at=like.created_at,
            profile=profiles[like.from_user_id],
        )
        for like in likes
        if like.from_user_id in profiles
    ]


async def sent_likes(session: AsyncSession, user: Me) -> list[SentLike]:
    """My likes still waiting for an answer. A pass looks the same: the liker is never told."""
    hidden = await hide_service.hidden_ids(session, user.id)
    likes = [
        like
        for like in await repository.likes_from(session, user.id, LOOKS_PENDING)
        if like.to_user_id not in hidden
    ]
    profiles = await profile_service.public_profiles(
        session, user.id, [like.to_user_id for like in likes]
    )
    return [
        SentLike(
            id=like.id,
            nickname=profiles[like.to_user_id].nickname,
            liked=_liked(like),
            comment=like.comment,
            created_at=like.created_at,
            has_blurred_photo=profiles[like.to_user_id].has_blurred_photo,
        )
        for like in likes
        if like.to_user_id in profiles
    ]


async def take_back(session: AsyncSession, user: Me, like_id: uuid.UUID, now: datetime) -> None:
    """Withdraw a like still waiting for an answer. They stop seeing it; nobody is told."""
    like = await repository.get_like_for_update(session, like_id)
    if like is None or like.from_user_id != user.id or like.status not in LOOKS_PENDING:
        raise LikeNotFound
    if await hide_service.is_hidden(session, user.id, like.to_user_id):
        raise LikeNotFound
    like.status = LikeStatus.WITHDRAWN
    like.decided_at = now
    await session.commit()


async def sent_photo(session: AsyncSession, user: Me, like_id: uuid.UUID) -> bytes:
    """The blurred photo of someone I liked, while the like waits (or looks like it does)."""
    like = await repository.get_like_by_id(session, like_id)
    if like is None or like.from_user_id != user.id or like.status not in LOOKS_PENDING:
        raise LikeNotFound
    if await hide_service.is_hidden(session, user.id, like.to_user_id):
        raise LikeNotFound
    return await profile_service.blurred_photo(session, user.id, like.to_user_id)


async def match_back(
    session: AsyncSession, user: Me, like_id: uuid.UUID, now: datetime
) -> MatchResult:
    like = await _waiting_for(session, user, like_id)
    like.status = LikeStatus.MATCHED
    like.decided_at = now
    match_id = await repository.add_match(session, *sorted((like.from_user_id, user.id)))
    await notification_service.notify(session, like.from_user_id, Event.MATCH, "/app/chats")
    await session.commit()
    return MatchResult(match_id=match_id)


async def pass_like(session: AsyncSession, user: Me, like_id: uuid.UUID, now: datetime) -> None:
    """Silent: the person who liked is never told."""
    like = await _waiting_for(session, user, like_id)
    like.status = LikeStatus.PASSED
    like.decided_at = now
    await session.commit()


def _liked(like: Like) -> Liked:
    return Liked(
        kind=LikedKind(like.kind),
        question=like.question,
        answer=like.answer,
        guess_kind=GuessKind(like.guess_kind) if like.guess_kind else None,
    )


async def _waiting_for(session: AsyncSession, user: Me, like_id: uuid.UUID) -> Like:
    like = await repository.get_like_for_update(session, like_id)
    # Someone else's like looks exactly like a missing one.
    if like is None or like.to_user_id != user.id:
        raise LikeNotFound
    if await hide_service.is_hidden(session, user.id, like.from_user_id):
        raise LikeNotFound
    if like.status != LikeStatus.PENDING:
        raise LikeAlreadyAnswered
    return like
