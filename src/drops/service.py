"""Tonight's drop: a few profiles each night at 9 PM. Like a prompt or pass.

The drop is built the first time someone opens the app after 9 PM, and saved, so a
refresh or a restart shows the same people. If fewer than DROP_SIZE people fit when it's
built (early days), it tops up as new people finish their profiles. At 9 PM `alert_tonight`
queues a push for everyone with a finished profile; the drop itself is still built on open.
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
from src.hides import service as hide_service
from src.matches import service as match_service
from src.matches.constants import LikedKind
from src.matches.schemas import Liked
from src.notifications import service as notification_service
from src.notifications.constants import DROP_ALERT_UNTIL_HOUR
from src.profiles import service as profile_service


def drop_date_for(now: datetime) -> date:
    """The drop open at `now`: today's if it's past 9 PM college time, else yesterday's."""
    local = now.astimezone(COLLEGE_TZ)
    return local.date() if local.hour >= DROP_HOUR else local.date() - timedelta(days=1)


def next_drop_at(now: datetime) -> datetime:
    opens = datetime.combine(drop_date_for(now) + timedelta(days=1), time(DROP_HOUR), COLLEGE_TZ)
    return opens.astimezone(now.tzinfo)


async def alert_tonight(session: AsyncSession, now: datetime) -> int:
    """Between 9 PM and midnight college time, queue tonight's alert (once a night)."""
    local = now.astimezone(COLLEGE_TZ)
    if not DROP_HOUR <= local.hour <= DROP_ALERT_UNTIL_HOUR:
        return 0
    return await notification_service.announce_drop(session, drop_date_for(now), "/app/tonight")


async def tonight(session: AsyncSession, user: Me, now: datetime) -> Tonight:
    drop_date = drop_date_for(now)
    await repository.lock_viewer(session, user.id)
    hidden = await hide_service.hidden_ids(session, user.id)
    items = await repository.items(session, user.id, drop_date)
    if len(items) < DROP_SIZE:
        items += await _top_up(session, user.id, drop_date, items, hidden)
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
            # Someone hidden after the drop was built drops out of it too.
            if i.shown_user_id in profiles and i.shown_user_id not in hidden
        ],
    )


async def like(
    session: AsyncSession, user: Me, item_id: uuid.UUID, body: LikeRequest, now: datetime
) -> LikeResult:
    item = await _open_item(session, user, item_id, now)
    liked = await _liked(session, user.id, item.shown_user_id, body)
    matched = await match_service.send_like(
        session, user.id, item.shown_user_id, liked, body.comment, now
    )
    item.decision = Decision.LIKED
    item.decided_at = now
    await session.commit()
    return LikeResult(matched=matched)


async def _liked(
    session: AsyncSession, user_id: uuid.UUID, owner_id: uuid.UUID, body: LikeRequest
) -> Liked:
    if body.guess_card_id is not None:
        card = await profile_service.guessed_card_of(session, owner_id, body.guess_card_id, user_id)
        return Liked(
            kind=LikedKind.GUESS, question=card.question, answer=card.answer, guess_kind=card.kind
        )
    assert body.prompt_id is not None  # LikeRequest allows exactly one
    prompt = await profile_service.prompt_of(session, owner_id, body.prompt_id)
    return Liked(
        kind=LikedKind.PROMPT, question=prompt.question, answer=prompt.answer, guess_kind=None
    )


async def pass_on(session: AsyncSession, user: Me, item_id: uuid.UUID, now: datetime) -> None:
    item = await _open_item(session, user, item_id, now)
    item.decision = Decision.PASSED
    item.decided_at = now
    await session.commit()


async def in_tonight(
    session: AsyncSession, viewer_id: uuid.UUID, owner_id: uuid.UUID, now: datetime
) -> bool:
    """Whether the owner is in the viewer's drop that's open now (answered or not)."""
    item = await repository.item_for(session, viewer_id, owner_id, drop_date_for(now))
    return item is not None and not await hide_service.is_hidden(session, viewer_id, owner_id)


async def blurred_photo(
    session: AsyncSession, user: Me, item_id: uuid.UUID, now: datetime
) -> bytes:
    """The blurred photo of someone in tonight's drop. Answered items still count."""
    item = await repository.get_item(session, item_id)
    if item is None or item.viewer_id != user.id or item.drop_date != drop_date_for(now):
        raise DropItemNotFound
    if await hide_service.is_hidden(session, user.id, item.shown_user_id):
        raise DropItemNotFound
    return await profile_service.blurred_photo(session, user.id, item.shown_user_id)


async def _top_up(
    session: AsyncSession,
    viewer_id: uuid.UUID,
    drop_date: date,
    items: list[DropItem],
    hidden: set[uuid.UUID],
) -> list[DropItem]:
    since = drop_date - timedelta(days=RESHOW_AFTER_DAYS)
    exclude = set(await repository.seen_ids(session, viewer_id, since)) | hidden
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
    if await hide_service.is_hidden(session, user.id, item.shown_user_id):
        raise DropItemNotFound
    if item.decision is not None or item.drop_date != drop_date_for(now):
        raise DropItemClosed("This drop has moved on")
    return item
