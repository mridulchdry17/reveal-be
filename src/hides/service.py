"""The hide list: people a student never wants to see, or be seen by, on Reveal.

Symmetric and silent (product rule 6). If either of two students has the other's email,
phone or Instagram on their list, neither appears in the other's drop or Likes, and
neither can guess the other's cards. Nobody is told, and adding someone says nothing
about whether they're on Reveal. Live matches carry on: block is the tool for those.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import service as auth_service
from src.auth.schemas import Me
from src.hides import repository
from src.hides.constants import HIDE_LIST_MAX
from src.hides.exceptions import HiddenContactNotFound, HideListFull
from src.hides.schemas import HiddenOut, HideList, HideRequest
from src.identity import IdentityKind, fingerprint
from src.profiles import service as profile_service


async def my_list(session: AsyncSession, user: Me) -> HideList:
    rows = await repository.list_for(session, user.id)
    return HideList(
        items=[HiddenOut.model_validate(r, from_attributes=True) for r in rows], max=HIDE_LIST_MAX
    )


async def hide(session: AsyncSession, user: Me, body: HideRequest) -> HideList:
    """Add someone. Adding the same person twice is a no-op."""
    if await repository.count_for(session, user.id) >= HIDE_LIST_MAX:
        raise HideListFull(f"You can hide up to {HIDE_LIST_MAX} people")
    await repository.add(
        session, user.id, body.kind, fingerprint(body.kind, body.value), mask(body.kind, body.value)
    )
    await session.commit()
    return await my_list(session, user)


async def unhide(session: AsyncSession, user: Me, entry_id: uuid.UUID) -> HideList:
    if not await repository.remove(session, user.id, entry_id):
        raise HiddenContactNotFound
    await session.commit()
    return await my_list(session, user)


async def hidden_ids(session: AsyncSession, user_id: uuid.UUID) -> set[uuid.UUID]:
    """Everyone hidden from this user, in either direction."""
    mine = await repository.fingerprints_of(session, user_id)
    found = set(await auth_service.ids_with_email_fingerprints(session, mine))
    found |= set(await profile_service.ids_with_contact_fingerprints(session, mine))
    found |= set(await repository.owners_hiding(session, await _fingerprints_for(session, user_id)))
    found.discard(user_id)
    return found


async def is_hidden(session: AsyncSession, user_id: uuid.UUID, other_id: uuid.UUID) -> bool:
    return other_id in await hidden_ids(session, user_id)


async def _fingerprints_for(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    """Every fingerprint someone could have put on a list to hide this user."""
    fps = [
        fingerprint(IdentityKind.EMAIL, e) for e in await auth_service.emails_of(session, user_id)
    ]
    contact = await profile_service.contact_of(session, user_id)
    if contact:
        fps.append(fingerprint(IdentityKind(contact[0]), contact[1]))
    return fps


def mask(kind: IdentityKind, value: str) -> str:
    """Enough to tell entries apart, not enough to read them back."""
    if kind == IdentityKind.EMAIL:
        local, _, domain = value.partition("@")
        return f"{local[:2]}•••@{domain}"
    if kind == IdentityKind.PHONE:
        return f"{value[:2]}••••••{value[-2:]}"
    return f"@{value[:2]}•••"
