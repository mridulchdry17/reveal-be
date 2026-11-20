import csv
import io
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.schemas import ErrorResponse
from src.security import require_admin
from src.waitlist import service
from src.waitlist.dependencies import limit_joins
from src.waitlist.schemas import WaitlistJoinRequest, WaitlistJoinResponse

router = APIRouter(prefix="/waitlist", tags=["waitlist"])


@router.post(
    "",
    response_model=WaitlistJoinResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Join the waitlist",
    dependencies=[Depends(limit_joins)],
    responses={
        200: {"model": WaitlistJoinResponse, "description": "Already on the list"},
        409: {"model": ErrorResponse, "description": "Details belong to another entry"},
        429: {"model": ErrorResponse, "description": "Too many attempts"},
    },
)
async def join_waitlist(
    body: WaitlistJoinRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WaitlistJoinResponse:
    result = await service.join(session, body)
    if result.already_joined:
        response.status_code = status.HTTP_200_OK
    return result


@router.get(
    "/export",
    summary="Download the waitlist as CSV (admin)",
    dependencies=[Depends(require_admin)],
    include_in_schema=False,
)
async def export_waitlist(session: Annotated[AsyncSession, Depends(get_session)]) -> Response:
    rows = await service.export(session)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["enrollment_number", "email", "joined_at"])
    for row in rows:
        writer.writerow([row.enrollment_number, row.email, row.joined_at.isoformat()])
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="waitlist.csv"'},
    )
