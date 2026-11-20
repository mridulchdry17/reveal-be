from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.waitlist import repository
from src.waitlist.exceptions import AlreadyRegistered
from src.waitlist.models import WaitlistEntry
from src.waitlist.schemas import WaitlistExportRow, WaitlistJoinRequest, WaitlistJoinResponse


async def join(session: AsyncSession, request: WaitlistJoinRequest) -> WaitlistJoinResponse:
    """Add someone to the waitlist.

    Joining again with the same enrollment number AND email returns the existing place.
    If only one of the two is already taken, that's someone else's entry: refuse without
    saying which one, so the form can't be used to look people up.
    """
    existing = await _existing_place(session, request)
    if existing is not None:
        return existing

    entry = WaitlistEntry(enrollment_number=request.enrollment_number, email=request.email)
    try:
        await repository.add(session, entry)
        await session.commit()
    except IntegrityError:
        # Someone submitted the same details at the same moment.
        await session.rollback()
        existing = await _existing_place(session, request)
        if existing is None:
            raise
        return existing

    position = await repository.position_of(session, entry.id)
    return WaitlistJoinResponse(position=position, already_joined=False)


async def _existing_place(
    session: AsyncSession, request: WaitlistJoinRequest
) -> WaitlistJoinResponse | None:
    matches = await repository.find_matching(session, request.enrollment_number, request.email)
    if not matches:
        return None
    for entry in matches:
        if entry.enrollment_number == request.enrollment_number and entry.email == request.email:
            position = await repository.position_of(session, entry.id)
            return WaitlistJoinResponse(position=position, already_joined=True)
    raise AlreadyRegistered(
        "This enrollment number or email is already on the list with different details."
    )


async def export(session: AsyncSession) -> list[WaitlistExportRow]:
    entries = await repository.list_all(session)
    return [
        WaitlistExportRow(
            enrollment_number=entry.enrollment_number,
            email=entry.email,
            joined_at=entry.created_at,
        )
        for entry in entries
    ]
