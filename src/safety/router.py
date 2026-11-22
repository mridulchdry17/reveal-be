import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import verified_user
from src.auth.schemas import Me
from src.clock import now
from src.database import get_session
from src.safety import service
from src.safety.schemas import ReportRequest
from src.schemas import ErrorResponse

router = APIRouter(prefix="/matches", tags=["safety"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Not signed in"},
    403: {"model": ErrorResponse, "description": "Not a verified student yet"},
    404: {"model": ErrorResponse, "description": "No such live match"},
}

Student = Annotated[Me, Depends(verified_user)]
Session = Annotated[AsyncSession, Depends(get_session)]
Now = Annotated[datetime, Depends(now)]


@router.post(
    "/{match_id}/block",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Block: the chat ends for both and you never see each other again",
    responses=_ERRORS,
)
async def block(match_id: uuid.UUID, user: Student, session: Session, at: Now) -> None:
    await service.block(session, user, match_id, at)


@router.post(
    "/{match_id}/report",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Report to admins. Also blocks",
    responses=_ERRORS,
)
async def report(
    match_id: uuid.UUID, body: ReportRequest, user: Student, session: Session, at: Now
) -> None:
    await service.report(session, user, match_id, body, at)
