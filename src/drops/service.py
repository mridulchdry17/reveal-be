"""Tonight's drop: a few profiles each night at 9 PM. Like a prompt or pass.

The drop is built the first time someone opens the app after 9 PM, and saved, so a
refresh or a restart shows the same people. If fewer than DROP_SIZE people fit when it's
built (early days), it tops up as new people finish their profiles. Push notifications
will need a 9 PM job; this stays the place that decides who's in a drop.
"""

import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.schemas import Me
from src.drops import repository
from src.drops.constants import COLLEGE_TZ, DROP_HOUR, DROP_SIZE, RESHOW_AFTER_DAYS, Decision
from src.drops.exceptions import DropItemClosed, DropItemNotFound
from src.drops.models import DropItem
from src.drops.schemas import DropItemOut, LikeRequest, LikeResult, Tonight
from src.matches import service as match_service
from src.profiles import service as profile_service


def drop_date_for(now: datetime) -> date:
    """The drop open at `now`: today's if it's past 9 PM college time, else yesterday's."""
    local = now.astimezone(COLLEGE_TZ)
    return local.date() if local.hour >= DROP_HOUR else local.date() - timedelta(days=1)


def next_drop_at(now: datetime) -> datetime:
    opens = datetime.combine(drop_date_for(now) + timedelta(days=1), time(DROP_HOUR), COLLEGE_TZ)
    return opens.astimezone(now.tzinfo)


async def tonight(session: AsyncSession, user: Me, now: datetime) -> Tonight:
    drop_date = drop_date_for(now)
    await repository.lock_viewer(session, user.id)
    items = await repository.items(session, user.id, drop_date)
    if len(items) < DROP_SIZE:
        items += await _top_up(session, user.id, drop_date, items)
    await session.commit()
    profiles = await profile_service.public_profiles(
        session, user.id, [i.shown_user_id for i in items]
    )
    return Tonight(
        drop_date=drop_date,
        next_drop_at=next_drop_at(now),
        items=[
            DropItemOut(
                id=i.id,
                decision=Decision(i.decision) if i.decision else None,
                profile=profiles[i.shown_user_id],
            )
            for i in items
            if i.shown_user_id in profiles
        ],
    )


async def like(
    session: AsyncSession, user: Me, item_id: uuid.UUID, body: LikeRequest, now: datetime
) -> LikeResult:
    item = await _open_item(session, user, item_id, now)
    prompt = await profile_service.prompt_of(session, item.shown_user_id, body.prompt_id)
    matched = await match_service.send_like(
        session, user.id, item.shown_user_id, prompt, body.comment, now
    )
    item.decision = Decision.LIKED
    item.decided_at = now
    await session.commit()
    return LikeResult(matched=matched)


async def pass_on(session: AsyncSession, user: Me, item_id: uuid.UUID, now: datetime) -> None:
    item = await _open_item(session, user, item_id, now)
    item.decision = Decision.PASSED
    item.decided_at = now
    await session.commit()


async def _top_up(
    session: AsyncSession, viewer_id: uuid.UUID, drop_date: date, items: list[DropItem]
) -> list[DropItem]:
    since = drop_date - timedelta(days=RESHOW_AFTER_DAYS)
    exclude = set(await repository.seen_ids(session, viewer_id, since))
    exclude |= set(await match_service.connected_ids(session, viewer_id))
    picked = await profile_service.drop_candidates(
        session, viewer_id, list(exclude), DROP_SIZE - len(items)
    )
    new = [
        DropItem(
            viewer_id=viewer_id, shown_user_id=uid, drop_date=drop_date, position=len(items) + n
        )
        for n, uid in enumerate(picked)
    ]
    await repository.add_items(session, new)
    return new


async def _open_item(
    session: AsyncSession, user: Me, item_id: uuid.UUID, now: datetime
) -> DropItem:
    item = await repository.get_item(session, item_id)
    if item is None or item.viewer_id != user.id:
        raise DropItemNotFound
    if item.decision is not None or item.drop_date != drop_date_for(now):
        raise DropItemClosed("This drop has moved on")
    return item
