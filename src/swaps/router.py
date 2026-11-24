import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import verified_user
from src.auth.schemas import Me
from src.clock import now
from src.database import get_session
from src.profiles.constants import Card
from src.schemas import ErrorResponse
from src.swaps import service
from src.swaps.schemas import ProposeSwap, SwapBoard

router = APIRouter(prefix="/chats/{match_id}/swaps", tags=["swaps"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Not signed in"},
    403: {"model": ErrorResponse, "description": "Not a verified student yet"},
    404: {"model": ErrorResponse, "description": "No such live match, or no request to answer"},
    409: {"model": ErrorResponse, "description": "That card can't be swapped right now"},
}

Student = Annotated[Me, Depends(verified_user)]
Session = Annotated[AsyncSession, Depends(get_session)]
Now = Annotated[datetime, Depends(now)]


@router.post(
    "",
    response_model=SwapBoard,
    status_code=status.HTTP_200_OK,
    summary="Ask to swap a card (says yes if they already asked for it)",
    responses=_ERRORS,
)
async def propose(
    match_id: uuid.UUID, body: ProposeSwap, user: Student, session: Session, at: Now
) -> SwapBoard:
    return await service.propose(session, user, match_id, body.card, at)


@router.post(
    "/{card}/accept",
    response_model=SwapBoard,
    status_code=status.HTTP_200_OK,
    summary="Swap: open this card for both of us",
    responses=_ERRORS,
)
async def accept(
    match_id: uuid.UUID, card: Card, user: Student, session: Session, at: Now
) -> SwapBoard:
    return await service.accept(session, user, match_id, card, at)


@router.post(
    "/{card}/decline",
    response_model=SwapBoard,
    status_code=status.HTTP_200_OK,
    summary="Not yet: nothing opens",
    responses=_ERRORS,
)
async def decline(
    match_id: uuid.UUID, card: Card, user: Student, session: Session, at: Now
) -> SwapBoard:
    return await service.decline(session, user, match_id, card, at)
