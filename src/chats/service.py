"""Chat between matched students. Either person can write first; there's no time limit."""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.schemas import Me
from src.chats import repository
from src.chats.constants import THREAD_LIMIT
from src.chats.models import Message
from src.chats.schemas import ChatSummary, ChatThread, MessageOut
from src.matches import service as match_service
from src.matches.exceptions import MatchNotFound
from src.notifications import service as notification_service
from src.notifications.constants import Event
from src.profiles import service as profile_service
from src.swaps import service as swap_service


async def chats(session: AsyncSession, user: Me) -> list[ChatSummary]:
    """My live matches, most recent activity first."""
    matches = await match_service.live_matches(session, user.id)
    ids = [m.id for m in matches]
    last = await repository.last_message_per_match(session, ids) if ids else {}
    seen = await repository.reads(session, user.id, ids) if ids else {}
    opened = await swap_service.opened_cards(session, matches)
    profiles = await profile_service.public_profiles(
        session, user.id, [m.other_user_id for m in matches], opened
    )
    rows = [
        ChatSummary(
            match_id=m.id,
            profile=profiles[m.other_user_id],
            matched_at=m.matched_at,
            last_message=_out(last[m.id], user) if m.id in last else None,
            unread=m.id in last
            and last[m.id].sender_id != user.id
            and seen.get(m.id) != last[m.id].id,
        )
        for m in matches
        if m.other_user_id in profiles
    ]
    rows.sort(
        key=lambda r: r.last_message.sent_at if r.last_message else r.matched_at, reverse=True
    )
    return rows


async def thread(session: AsyncSession, user: Me, match_id: uuid.UUID) -> ChatThread:
    match = await match_service.live_match(session, user.id, match_id)
    opened = await swap_service.opened_cards(session, [match])
    profiles = await profile_service.public_profiles(
        session, user.id, [match.other_user_id], opened
    )
    if match.other_user_id not in profiles:
        raise MatchNotFound
    messages = await repository.latest_messages(session, match.id, THREAD_LIMIT)
    return ChatThread(
        match_id=match.id,
        profile=profiles[match.other_user_id],
        matched_at=match.matched_at,
        messages=[_out(m, user) for m in messages],
        swaps=await swap_service.board(session, user.id, match),
    )


async def send(session: AsyncSession, user: Me, match_id: uuid.UUID, body: str) -> MessageOut:
    match = await match_service.live_match(session, user.id, match_id)
    message = Message(match_id=match.id, sender_id=user.id, body=body)
    await repository.add_message(session, message)
    await repository.set_read(session, match.id, user.id, message.id)
    await notification_service.notify(
        session,
        match.other_user_id,
        Event.MESSAGE,
        f"/app/chats/{match.id}",
        tag=f"chat-{match.id}",
    )
    await session.commit()
    await session.refresh(message)
    return _out(message, user)


async def mark_read(session: AsyncSession, user: Me, match_id: uuid.UUID) -> None:
    match = await match_service.live_match(session, user.id, match_id)
    latest = await repository.latest_messages(session, match.id, 1)
    if latest:
        await repository.set_read(session, match.id, user.id, latest[0].id)
        await session.commit()


def _unread(last: Message | None, seen_id: uuid.UUID | None, user: Me) -> bool:
    return last is not None and last.sender_id != user.id and seen_id != last.id


def _last_activity(row: ChatSummary) -> datetime:
    return row.last_message.sent_at if row.last_message else row.matched_at


def _out(message: Message, user: Me) -> MessageOut:
    return MessageOut(
        id=message.id,
        body=message.body,
        mine=message.sender_id == user.id,
        sent_at=message.created_at,
    )
