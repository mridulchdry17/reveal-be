from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import verified_user
from src.auth.schemas import Me
from src.config import settings
from src.database import get_session
from src.profiles import service
from src.profiles.dependencies import limit_media_uploads
from src.profiles.schemas import (
    BasicsUpdate,
    CardsUpdate,
    Contact,
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
    summary="Card contents",
    responses=_SAVE_ERRORS,
)
async def update_cards(body: CardsUpdate, user: Student, session: Session) -> MyProfile:
    return await service.update_cards(session, user, body)


@router.put(
    "/me/photo",
    response_model=MyProfile,
    status_code=status.HTTP_200_OK,
    summary="Card 6: my photo, private until the photo swap",
    dependencies=[Depends(limit_media_uploads)],
    responses={
        **_ERRORS,
        413: {"model": ErrorResponse, "description": "Photo too large"},
        422: {"model": ErrorResponse, "description": "Not a JPEG, PNG or WebP photo"},
        429: {"model": ErrorResponse, "description": "Too many uploads"},
    },
)
async def update_photo(
    photo: Annotated[UploadFile, File(description="JPEG, PNG or WebP")],
    user: Student,
    session: Session,
) -> MyProfile:
    # One byte past the limit lets the service tell "too large" without reading it all.
    data = await photo.read(settings.profile_photo_max_bytes + 1)
    return await service.update_photo(session, user, data)


@router.get(
    "/me/photo",
    response_class=Response,
    status_code=status.HTTP_200_OK,
    summary="My own photo (JPEG, never cached)",
    responses={
        **_ERRORS,
        200: {"content": {"image/jpeg": {}}, "description": "The photo"},
        404: {"model": ErrorResponse, "description": "No photo yet"},
    },
)
async def my_photo(user: Student, session: Session) -> Response:
    data = await service.my_photo(session, user)
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store, private"})


@router.delete(
    "/me/photo",
    response_model=MyProfile,
    status_code=status.HTTP_200_OK,
    summary="Remove my photo",
    responses=_ERRORS,
)
async def remove_photo(user: Student, session: Session) -> MyProfile:
    return await service.remove_photo(session, user)


@router.put(
    "/me/contact",
    response_model=MyProfile,
    status_code=status.HTTP_200_OK,
    summary="Card 7: Instagram or phone, sealed until the contact swap",
    responses=_SAVE_ERRORS,
)
async def update_contact(body: Contact, user: Student, session: Session) -> MyProfile:
    return await service.update_contact(session, user, body)


@router.delete(
    "/me/contact",
    response_model=MyProfile,
    status_code=status.HTTP_200_OK,
    summary="Remove card 7",
    responses=_ERRORS,
)
async def remove_contact(user: Student, session: Session) -> MyProfile:
    return await service.remove_contact(session, user)


@router.put(
    "/me/preferences",
    response_model=MyProfile,
    status_code=status.HTTP_200_OK,
    summary="Who to show me, and safety choices",
    responses=_SAVE_ERRORS,
)
async def update_preferences(body: PreferencesUpdate, user: Student, session: Session) -> MyProfile:
    return await service.update_preferences(session, user, body)
