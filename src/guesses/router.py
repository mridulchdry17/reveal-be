import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import verified_user
from src.auth.schemas import Me
from src.clock import now
from src.database import get_session
from src.guesses import service
from src.guesses.schemas import GuessIn, GuessResult
from src.schemas import ErrorResponse

router = APIRouter(prefix="/guesses", tags=["guesses"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Not signed in"},
    403: {"model": ErrorResponse, "description": "Not a verified student yet"},
    404: {"model": ErrorResponse, "description": "No such card, or not someone you can see"},
    409: {"model": ErrorResponse, "description": "Already guessed (code already_guessed)"},
}

Student = Annotated[Me, Depends(verified_user)]
Session = Annotated[AsyncSession, Depends(get_session)]
Now = Annotated[datetime, Depends(now)]


@router.post(
    "/{card_id}",
    response_model=GuessResult,
    status_code=status.HTTP_200_OK,
    summary="Guess one of their cards (one try)",
    responses=_ERRORS,
)
async def guess(
    card_id: uuid.UUID, body: GuessIn, user: Student, session: Session, at: Now
) -> GuessResult:
    return await service.guess(session, user, card_id, body.pick, at)
