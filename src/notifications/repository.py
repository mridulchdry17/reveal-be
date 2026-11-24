import uuid
from collections.abc import Collection
from datetime import date

from sqlalchemy import delete, exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.notifications.models import DropAlert, PushOutbox, PushSubscription


async def save_subscription(
    session: AsyncSession, user_id: uuid.UUID, endpoint: str, p256dh: str, auth: str
) -> None:
    """One row per device: a device that signs in to another account moves to it."""
    stmt = insert(PushSubscription).values(
        id=uuid.uuid4(), user_id=user_id, endpoint=endpoint, p256dh=p256dh, auth=auth
    )
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=["endpoint"],
            set_={"user_id": user_id, "p256dh": p256dh, "auth": auth},
        )
    )


async def delete_subscription(session: AsyncSession, user_id: uuid.UUID, endpoint: str) -> None:
    await session.execute(
        delete(PushSubscription).where(
            PushSubscription.user_id == user_id, PushSubscription.endpoint == endpoint
        )
    )


async def delete_subscriptions(session: AsyncSession, ids: Collection[uuid.UUID]) -> None:
    if ids:
        await session.execute(delete(PushSubscription).where(PushSubscription.id.in_(list(ids))))


async def subscriptions_for(
    session: AsyncSession, user_ids: Collection[uuid.UUID]
) -> list[PushSubscription]:
    rows = await session.scalars(
        select(PushSubscription).where(PushSubscription.user_id.in_(list(user_ids)))
    )
    return list(rows)


async def has_subscription(session: AsyncSession, user_id: uuid.UUID) -> bool:
    found = await session.scalar(select(exists().where(PushSubscription.user_id == user_id)))
    return bool(found)


async def subscribed_user_ids(session: AsyncSession) -> list[uuid.UUID]:
    return list(await session.scalars(select(PushSubscription.user_id).distinct()))


async def is_queued(session: AsyncSession, user_id: uuid.UUID, tag: str) -> bool:
    found = await session.scalar(
        select(exists().where(PushOutbox.user_id == user_id, PushOutbox.tag == tag))
    )
    return bool(found)


async def queue(session: AsyncSession, rows: list[PushOutbox]) -> None:
    session.add_all(rows)
    await session.flush()


async def claim(session: AsyncSession, limit: int) -> list[PushOutbox]:
    """The oldest waiting notifications, locked so another sender skips them."""
    rows = await session.scalars(
        select(PushOutbox)
        .order_by(PushOutbox.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list(rows)


async def delete_outbox(session: AsyncSession, ids: Collection[uuid.UUID]) -> None:
    if ids:
        await session.execute(delete(PushOutbox).where(PushOutbox.id.in_(list(ids))))


async def claim_drop_alert(session: AsyncSession, drop_date: date) -> bool:
    """True the first time for this night; False if the alert was already queued."""
    result = await session.execute(
        insert(DropAlert)
        .values(id=uuid.uuid4(), drop_date=drop_date)
        .on_conflict_do_nothing(index_elements=["drop_date"])
        .returning(DropAlert.id)
    )
    return result.scalar() is not None
