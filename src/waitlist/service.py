from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.waitlist import repository
from src.waitlist.models import WaitlistEntry
from src.waitlist.schemas import WaitlistExportRow, WaitlistJoinRequest, WaitlistJoinResponse


async def join(session: AsyncSession, request: WaitlistJoinRequest) -> WaitlistJoinResponse:
    """Add someone to the waitlist.

    - Same enrollment number AND email again: return the existing place.
    - Only one of the two is already taken: that's someone else's entry. Answer exactly
      like a fresh join and save nothing, so the form can never confirm that a given
      student is on the list. The real owner can reach us to sort it out.
    """
    outcome = await _check_existing(session, request)
    if outcome is not None:
        return outcome

    entry = WaitlistEntry(
        enrollment_number=request.enrollment_number,
        email=request.email,
        source=request.source,
    )
    try:
        await repository.add(session, entry)
        await session.commit()
    except IntegrityError:
        # Someone submitted overlapping details at the same moment.
        await session.rollback()
        outcome = await _check_existing(session, request)
        if outcome is None:
            raise
        return outcome

    position = await repository.position_of(session, entry.id)
    return WaitlistJoinResponse(position=position, already_joined=False)


async def _check_existing(
    session: AsyncSession, request: WaitlistJoinRequest
) -> WaitlistJoinResponse | None:
    matches = await repository.find_matching(session, request.enrollment_number, request.email)
    if not matches:
        return None
    for entry in matches:
        if entry.enrollment_number == request.enrollment_number and entry.email == request.email:
            position = await repository.position_of(session, entry.id)
            return WaitlistJoinResponse(position=position, already_joined=True)
    return await _looks_like_a_new_join(session)


async def _looks_like_a_new_join(session: AsyncSession) -> WaitlistJoinResponse:
    position = await repository.count_all(session) + 1
    return WaitlistJoinResponse(position=position, already_joined=False)


async def export(session: AsyncSession) -> list[WaitlistExportRow]:
    entries = await repository.list_all(session)
    return [
        WaitlistExportRow(
            enrollment_number=entry.enrollment_number,
            email=entry.email,
            source=entry.source,
            joined_at=entry.created_at,
        )
        for entry in entries
    ]
