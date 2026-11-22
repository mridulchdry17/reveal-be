from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import verified_user
from src.auth.schemas import Me
from src.database import get_session
from src.profiles import service
from src.profiles.schemas import (
    BasicsUpdate,
    CardsUpdate,
    MyProfile,
    PreferencesUpdate,
    ProfileOptions,
    PromptsUpdate,
)
from src.schemas import ErrorResponse

router = APIRouter(prefix="/profile", tags=["profile"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Not signed in"},
    403: {"model": ErrorResponse, "description": "Not a verified student yet"},
}
# 422 keeps FastAPI's field-by-field validation shape, which the frontend maps to inputs.
_SAVE_ERRORS = _ERRORS

Student = Annotated[Me, Depends(verified_user)]
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/options", response_model=ProfileOptions, summary="Choices for the profile screens")
async def options() -> ProfileOptions:
    return service.options()


@router.get("/me", response_model=MyProfile, summary="My profile", responses=_ERRORS)
async def my_profile(user: Student, session: Session) -> MyProfile:
    return await service.my_profile(session, user)


@router.put(
    "/me/basics",
    response_model=MyProfile,
    status_code=status.HTTP_200_OK,
    summary="Nickname, vibe and interests",
    responses=_SAVE_ERRORS,
)
async def update_basics(body: BasicsUpdate, user: Student, session: Session) -> MyProfile:
    return await service.update_basics(session, user, body)


@router.put(
    "/me/prompts",
    response_model=MyProfile,
    status_code=status.HTTP_200_OK,
    summary="The three prompts",
    responses=_SAVE_ERRORS,
)
async def update_prompts(body: PromptsUpdate, user: Student, session: Session) -> MyProfile:
    return await service.update_prompts(session, user, body)


@router.put(
    "/me/cards",
    response_model=MyProfile,
    status_code=status.HTTP_200_OK,
    summary="Card contents and which are shown without a swap",
    responses=_SAVE_ERRORS,
)
async def update_cards(body: CardsUpdate, user: Student, session: Session) -> MyProfile:
    return await service.update_cards(session, user, body)


@router.put(
    "/me/preferences",
    response_model=MyProfile,
    status_code=status.HTTP_200_OK,
    summary="Who to show me, and safety choices",
    responses=_SAVE_ERRORS,
)
async def update_preferences(body: PreferencesUpdate, user: Student, session: Session) -> MyProfile:
    return await service.update_preferences(session, user, body)
