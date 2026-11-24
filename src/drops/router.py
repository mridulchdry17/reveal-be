import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import verified_user
from src.auth.schemas import Me
from src.clock import now
from src.database import get_session
from src.drops import service
from src.drops.schemas import LikeRequest, LikeResult, Tonight
from src.schemas import ErrorResponse

router = APIRouter(prefix="/drops", tags=["drops"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Not signed in"},
    403: {"model": ErrorResponse, "description": "Not a verified student yet"},
    409: {"model": ErrorResponse, "description": "Profile not finished"},
}
_ANSWER_ERRORS: dict[int | str, dict[str, Any]] = {
    **_ERRORS,
    404: {"model": ErrorResponse, "description": "Not in your drop, or the prompt is gone"},
    409: {"model": ErrorResponse, "description": "Already answered, or the drop has moved on"},
}

Student = Annotated[Me, Depends(verified_user)]
Session = Annotated[AsyncSession, Depends(get_session)]
Now = Annotated[datetime, Depends(now)]


@router.get("/tonight", response_model=Tonight, summary="Tonight's drop", responses=_ERRORS)
async def tonight(user: Student, session: Session, at: Now) -> Tonight:
    return await service.tonight(session, user, at)


@router.post(
    "/tonight/{item_id}/like",
    response_model=LikeResult,
    status_code=status.HTTP_200_OK,
    summary="Like one of their prompts, with an optional comment",
    responses=_ANSWER_ERRORS,
)
async def like(
    item_id: uuid.UUID, body: LikeRequest, user: Student, session: Session, at: Now
) -> LikeResult:
    return await service.like(session, user, item_id, body, at)


@router.post(
    "/tonight/{item_id}/pass",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Pass on someone in tonight's drop",
    responses=_ANSWER_ERRORS,
)
async def pass_on(item_id: uuid.UUID, user: Student, session: Session, at: Now) -> None:
    await service.pass_on(session, user, item_id, at)


@router.get(
    "/tonight/{item_id}/photo",
    response_class=Response,
    status_code=status.HTTP_200_OK,
    summary="Their photo, heavily blurred; clearer with each right guess (JPEG, never cached)",
    responses={
        **{k: v for k, v in _ERRORS.items() if k != 409},
        200: {"content": {"image/jpeg": {}}, "description": "Blurred photo"},
        404: {"model": ErrorResponse, "description": "Not in your drop, or no photo to show"},
    },
)
async def blurred_photo(item_id: uuid.UUID, user: Student, session: Session, at: Now) -> Response:
    data = await service.blurred_photo(session, user, item_id, at)
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store, private"})
