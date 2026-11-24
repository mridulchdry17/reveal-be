import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import verified_user
from src.auth.schemas import Me
from src.clock import now
from src.database import get_session
from src.matches import service
from src.matches.schemas import ReceivedLike
from src.schemas import ErrorResponse

router = APIRouter(prefix="/likes", tags=["likes"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Not signed in"},
    403: {"model": ErrorResponse, "description": "Not a verified student yet"},
}
_ANSWER_ERRORS: dict[int | str, dict[str, Any]] = {
    **_ERRORS,
    404: {"model": ErrorResponse, "description": "No such like for you"},
    409: {"model": ErrorResponse, "description": "Already answered"},
}

Student = Annotated[Me, Depends(verified_user)]
Session = Annotated[AsyncSession, Depends(get_session)]
Now = Annotated[datetime, Depends(now)]


@router.get("", response_model=list[ReceivedLike], summary="People who liked me", responses=_ERRORS)
async def received_likes(user: Student, session: Session) -> list[ReceivedLike]:
    return await service.received_likes(session, user)


@router.post(
    "/{like_id}/match",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Like them back: it's a match",
    responses=_ANSWER_ERRORS,
)
async def match_back(like_id: uuid.UUID, user: Student, session: Session, at: Now) -> None:
    await service.match_back(session, user, like_id, at)


@router.post(
    "/{like_id}/pass",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Pass. They're never told",
    responses=_ANSWER_ERRORS,
)
async def pass_like(like_id: uuid.UUID, user: Student, session: Session, at: Now) -> None:
    await service.pass_like(session, user, like_id, at)


@router.get(
    "/{like_id}/photo",
    response_class=Response,
    status_code=status.HTTP_200_OK,
    summary="Their photo, heavily blurred; clearer with each right guess (JPEG, never cached)",
    responses={
        **_ERRORS,
        200: {"content": {"image/jpeg": {}}, "description": "Blurred photo"},
        404: {"model": ErrorResponse, "description": "No such like for you, or no photo to show"},
    },
)
async def blurred_photo(like_id: uuid.UUID, user: Student, session: Session) -> Response:
    data = await service.blurred_photo(session, user, like_id)
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store, private"})


matches_router = APIRouter(prefix="/matches", tags=["matches"])


@matches_router.post(
    "/{match_id}/unmatch",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="End a match for both of you. The chat closes",
    responses={**_ERRORS, 404: {"model": ErrorResponse, "description": "No such live match"}},
)
async def unmatch(match_id: uuid.UUID, user: Student, session: Session, at: Now) -> None:
    await service.unmatch(session, user, match_id, at)
