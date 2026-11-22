import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on, insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.chats.models import ChatRead, Message


async def latest_messages(session: AsyncSession, match_id: uuid.UUID, limit: int) -> list[Message]:
    rows = await session.scalars(
        select(Message)
        .where(Message.match_id == match_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
    )
    return list(reversed(list(rows)))


async def last_message_per_match(
    session: AsyncSession, match_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, Message]:
    rows = await session.scalars(
        select(Message)
        .where(Message.match_id.in_(match_ids))
        .ext(distinct_on(Message.match_id))
        .order_by(Message.match_id, Message.created_at.desc(), Message.id.desc())
    )
    return {m.match_id: m for m in rows}


async def reads(
    session: AsyncSession, user_id: uuid.UUID, match_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, uuid.UUID]:
    rows = await session.execute(
        select(ChatRead.match_id, ChatRead.last_read_message_id).where(
            ChatRead.user_id == user_id, ChatRead.match_id.in_(match_ids)
        )
    )
    return {match_id: message_id for match_id, message_id in rows}


async def add_message(session: AsyncSession, message: Message) -> None:
    session.add(message)
    await session.flush()


async def set_read(
    session: AsyncSession, match_id: uuid.UUID, user_id: uuid.UUID, message_id: uuid.UUID
) -> None:
    await session.execute(
        insert(ChatRead)
        .values(
            id=uuid.uuid4(), match_id=match_id, user_id=user_id, last_read_message_id=message_id
        )
        .on_conflict_do_update(
            index_elements=["match_id", "user_id"], set_={"last_read_message_id": message_id}
        )
    )
