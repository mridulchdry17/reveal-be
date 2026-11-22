"""Likes and matches. A like waits in the other person's Likes list; liking back matches."""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.schemas import Me
from src.matches import repository
from src.matches.constants import LikeStatus
from src.matches.exceptions import AlreadyLiked, LikeAlreadyAnswered, LikeNotFound, MatchNotFound
from src.matches.models import Like, Match
from src.matches.schemas import MatchInfo, ReceivedLike
from src.profiles import service as profile_service
from src.profiles.schemas import PromptOut


async def send_like(
    session: AsyncSession,
    from_user_id: uuid.UUID,
    to_user_id: uuid.UUID,
    prompt: PromptOut,
    comment: str | None,
    now: datetime,
) -> bool:
    """Like someone's prompt. Returns True if it's a match. Doesn't commit: the caller does.

    If they had already liked me, this is a match straight away. If they had passed on me,
    my like is quietly filed as passed so it never reaches them again.
    """
    if await repository.get_like(session, from_user_id, to_user_id):
        raise AlreadyLiked("You've already liked them")
    theirs = await repository.get_like(session, to_user_id, from_user_id)
    status = LikeStatus.PENDING
    if theirs and theirs.status == LikeStatus.PASSED:
        status = LikeStatus.PASSED
    elif theirs:
        status = LikeStatus.MATCHED
        theirs.status = LikeStatus.MATCHED
        theirs.decided_at = now
    await repository.add_like(
        session,
        Like(
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            prompt_question=prompt.question,
            prompt_answer=prompt.answer,
            comment=comment,
            status=status,
            decided_at=now if status != LikeStatus.PENDING else None,
        ),
    )
    if status == LikeStatus.MATCHED:
        await repository.add_match(session, *sorted((from_user_id, to_user_id)))
    return status == LikeStatus.MATCHED


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
    transaction. With swaps, this is also where everything opened between them closes."""
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


async def connected_ids(session: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    """People this user already has history with, so the drop doesn't show them again."""
    return await repository.connected_ids(session, user_id)


async def received_likes(session: AsyncSession, user: Me) -> list[ReceivedLike]:
    likes = await repository.likes_to(session, user.id, LikeStatus.PENDING)
    profiles = await profile_service.public_profiles(
        session, user.id, [like.from_user_id for like in likes]
    )
    return [
        ReceivedLike(
            id=like.id,
            prompt_question=like.prompt_question,
            prompt_answer=like.prompt_answer,
            comment=like.comment,
            created_at=like.created_at,
            profile=profiles[like.from_user_id],
        )
        for like in likes
        if like.from_user_id in profiles
    ]


async def match_back(session: AsyncSession, user: Me, like_id: uuid.UUID, now: datetime) -> None:
    like = await _waiting_for(session, user, like_id)
    like.status = LikeStatus.MATCHED
    like.decided_at = now
    await repository.add_match(session, *sorted((like.from_user_id, user.id)))
    await session.commit()


async def pass_like(session: AsyncSession, user: Me, like_id: uuid.UUID, now: datetime) -> None:
    """Silent: the person who liked is never told."""
    like = await _waiting_for(session, user, like_id)
    like.status = LikeStatus.PASSED
    like.decided_at = now
    await session.commit()


async def _waiting_for(session: AsyncSession, user: Me, like_id: uuid.UUID) -> Like:
    like = await repository.get_like_by_id(session, like_id)
    # Someone else's like looks exactly like a missing one.
    if like is None or like.to_user_id != user.id:
        raise LikeNotFound
    if like.status != LikeStatus.PENDING:
        raise LikeAlreadyAnswered
    return like
