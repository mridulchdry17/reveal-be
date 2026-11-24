import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import verified_user
from src.auth.schemas import Me
from src.database import get_session
from src.hides import service
from src.hides.schemas import HideList, HideRequest
from src.schemas import ErrorResponse

router = APIRouter(prefix="/hides", tags=["hides"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Not signed in"},
    403: {"model": ErrorResponse, "description": "Not a verified student yet"},
}

Student = Annotated[Me, Depends(verified_user)]
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=HideList, summary="People you've hidden", responses=_ERRORS)
async def my_list(user: Student, session: Session) -> HideList:
    return await service.my_list(session, user)


@router.post(
    "",
    response_model=HideList,
    status_code=status.HTTP_200_OK,
    summary="Hide someone by email, phone or Instagram. Silent, and works both ways",
    responses={**_ERRORS, 409: {"model": ErrorResponse, "description": "List is full"}},
)
async def hide(body: HideRequest, user: Student, session: Session) -> HideList:
    return await service.hide(session, user, body)


@router.delete(
    "/{entry_id}",
    response_model=HideList,
    status_code=status.HTTP_200_OK,
    summary="Stop hiding someone",
    responses={**_ERRORS, 404: {"model": ErrorResponse, "description": "Not on your list"}},
)
async def unhide(entry_id: uuid.UUID, user: Student, session: Session) -> HideList:
    return await service.unhide(session, user, entry_id)
