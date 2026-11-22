import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.admin import service
from src.admin.schemas import (
    AdminActionOut,
    AdminReport,
    LetInRequest,
    LetInResult,
    RejectRequest,
    Review,
)
from src.auth.dependencies import admin_user
from src.auth.schemas import Me
from src.database import get_session
from src.schemas import ErrorResponse

router = APIRouter(prefix="/admin", tags=["admin"])

_ADMIN: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Not signed in"},
    403: {"model": ErrorResponse, "description": "Not an admin"},
}
_REVIEW: dict[int | str, dict[str, Any]] = {
    **_ADMIN,
    404: {"model": ErrorResponse, "description": "No such review"},
    409: {"model": ErrorResponse, "description": "Already reviewed"},
}

Admin = Annotated[Me, Depends(admin_user)]
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get(
    "/reviews",
    response_model=list[Review],
    summary="ID checks waiting for review, oldest first",
    responses=_ADMIN,
)
async def reviews(_: Admin, session: Session) -> list[Review]:
    return await service.reviews(session)


@router.get(
    "/reviews/{review_id}/photos/{kind}",
    response_class=FileResponse,
    summary="One photo of a review (admins only, never cached)",
    responses={**_ADMIN, 404: {"model": ErrorResponse, "description": "Photo not found"}},
)
async def review_photo(
    review_id: uuid.UUID, kind: Literal["selfie", "id_card"], _: Admin, session: Session
) -> FileResponse:
    path = await service.photo(session, review_id, kind)
    return FileResponse(path, headers={"Cache-Control": "no-store, private"})


@router.post(
    "/reviews/{review_id}/approve",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="ID and selfie match: verify the student and delete the photos",
    responses=_REVIEW,
)
async def approve(review_id: uuid.UUID, admin: Admin, session: Session) -> None:
    await service.approve(session, admin, review_id)


@router.post(
    "/reviews/{review_id}/reject",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reject with a reason the student sees; delete the photos",
    responses=_REVIEW,
)
async def reject(review_id: uuid.UUID, body: RejectRequest, admin: Admin, session: Session) -> None:
    await service.reject(session, admin, review_id, body.reason)


@router.post(
    "/let-in",
    response_model=LetInResult,
    summary="Verify a signed-in account directly, e.g. a first-year",
    responses={
        **_ADMIN,
        404: {"model": ErrorResponse, "description": "No account with that email"},
        409: {"model": ErrorResponse, "description": "Already verified"},
    },
)
async def let_in(body: LetInRequest, admin: Admin, session: Session) -> LetInResult:
    return await service.let_in(session, admin, body.email, body.note)


@router.get(
    "/actions",
    response_model=list[AdminActionOut],
    summary="Recent admin decisions, newest first",
    responses=_ADMIN,
)
async def actions(_: Admin, session: Session) -> list[AdminActionOut]:
    return await service.recent_actions(session)


@router.get(
    "/reports",
    response_model=list[AdminReport],
    summary="Students' reports, newest first",
    responses=_ADMIN,
)
async def reports(_: Admin, session: Session) -> list[AdminReport]:
    return await service.recent_reports(session)
