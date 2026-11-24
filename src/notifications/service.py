"""Push notifications: devices that said yes, and what's waiting to go out.

Other domains call `notify` inside their own transaction, so the notification is saved
with the event (a like, a match, a message) or not at all. `deliver` sends what's waiting;
`src.jobs` runs it every few seconds inside the API process (no Redis or worker yet: the
VM is small). Copy is generic (constants.COPY): never names, message text or photos.
"""

import asyncio
import json
import logging
import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.schemas import Me
from src.config import settings
from src.notifications import repository
from src.notifications.constants import (
    BATCH_SIZE,
    COPY,
    DEFAULT_TTL_SECONDS,
    MAX_ATTEMPTS,
    TITLE,
    TTL_SECONDS,
    Event,
)
from src.notifications.models import PushOutbox, PushSubscription
from src.notifications.schemas import PushConfig, SubscriptionIn
from src.notifications.webpush import Device, Sender
from src.profiles import service as profile_service

log = logging.getLogger(__name__)

# Push services answer these when a device has unsubscribed or the app was removed.
_GONE = {404, 410}


def config() -> PushConfig:
    return PushConfig(public_key=settings.vapid_public_key if settings.push_enabled else None)


async def subscribe(session: AsyncSession, user: Me, body: SubscriptionIn) -> None:
    await repository.save_subscription(
        session, user.id, body.endpoint, body.keys.p256dh, body.keys.auth
    )
    await session.commit()


async def unsubscribe(session: AsyncSession, user: Me, endpoint: str) -> None:
    await repository.delete_subscription(session, user.id, endpoint)
    await session.commit()


async def notify(
    session: AsyncSession, user_id: uuid.UUID, event: Event, url: str, tag: str | None = None
) -> None:
    """Queue a notification for everyone of this user's devices. Doesn't commit: the
    caller's transaction does, so it goes out only if the event really happened.

    One waits per user and tag: ten messages in a row are one notification, not ten.
    """
    if not settings.push_enabled or not await repository.has_subscription(session, user_id):
        return
    tag = tag or str(event)
    if await repository.is_queued(session, user_id, tag):
        return
    await repository.queue(session, [PushOutbox(user_id=user_id, event=event, url=url, tag=tag)])


async def announce_drop(session: AsyncSession, drop_date: date, url: str) -> int:
    """Queue tonight's alert for everyone who can open a drop, once per night. Commits."""
    if not settings.push_enabled or not await repository.claim_drop_alert(session, drop_date):
        await session.rollback()
        return 0
    ready = await profile_service.complete_user_ids(
        session, await repository.subscribed_user_ids(session)
    )
    await repository.queue(
        session,
        [PushOutbox(user_id=uid, event=Event.DROP, url=url, tag=Event.DROP) for uid in ready],
    )
    await session.commit()
    return len(ready)


async def deliver(session: AsyncSession, send: Sender) -> int:
    """Send one batch of waiting notifications. Returns how many it handled (0 = idle)."""
    rows = await repository.claim(session, BATCH_SIZE)
    if not rows:
        await session.rollback()
        return 0
    devices: dict[uuid.UUID, list[PushSubscription]] = {}
    for sub in await repository.subscriptions_for(session, {r.user_id for r in rows}):
        devices.setdefault(sub.user_id, []).append(sub)

    jobs = [(row, sub) for row in rows for sub in devices.get(row.user_id, [])]
    codes = await asyncio.gather(
        *(send(_device(sub), _payload(row), _ttl(row)) for row, sub in jobs)
    )
    gone = {sub.id for (_, sub), code in zip(jobs, codes, strict=True) if code in _GONE}
    failed = {
        row.id
        for (row, _), code in zip(jobs, codes, strict=True)
        if code in (0, 429) or code >= 500
    }

    done: list[uuid.UUID] = []
    for row in rows:
        row.attempts += 1
        if row.id not in failed or row.attempts >= MAX_ATTEMPTS:
            done.append(row.id)
    await repository.delete_subscriptions(session, gone)
    await repository.delete_outbox(session, done)
    await session.commit()
    if failed:
        log.info("push: %d to retry", len(failed))
    return len(rows)


def _device(sub: PushSubscription) -> Device:
    return Device(endpoint=sub.endpoint, p256dh=sub.p256dh, auth=sub.auth)


def _payload(row: PushOutbox) -> str:
    event = Event(row.event)
    return json.dumps({"title": TITLE, "body": COPY[event], "url": row.url, "tag": row.tag})


def _ttl(row: PushOutbox) -> int:
    return TTL_SECONDS.get(Event(row.event), DEFAULT_TTL_SECONDS)
