from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import current_user
from src.auth.schemas import Me
from src.config import settings
from src.database import get_session
from src.schemas import ErrorResponse
from src.verification import service
from src.verification.dependencies import limit_uploads
from src.verification.schemas import VerificationStatus

router = APIRouter(prefix="/verification", tags=["verification"])

_UNAUTHENTICATED: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Not signed in"}
}


@router.get(
    "/me",
    response_model=VerificationStatus,
    status_code=status.HTTP_200_OK,
    summary="Where my ID card check is",
    responses=_UNAUTHENTICATED,
)
async def my_status(
    user: Annotated[Me, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> VerificationStatus:
    return await service.status_for(session, user.id)


@router.post(
    "/id-card",
    response_model=VerificationStatus,
    status_code=status.HTTP_201_CREATED,
    summary="Send an ID card photo and a selfie for review",
    dependencies=[Depends(limit_uploads)],
    responses={
        **_UNAUTHENTICATED,
        409: {"model": ErrorResponse, "description": "Already verified or already waiting"},
        413: {"model": ErrorResponse, "description": "Photo too large"},
        422: {"model": ErrorResponse, "description": "Not a JPEG, PNG or WebP photo"},
        429: {"model": ErrorResponse, "description": "Too many attempts"},
    },
)
async def submit_id_card(
    selfie: Annotated[UploadFile, File(description="Selfie, JPEG/PNG/WebP")],
    id_card: Annotated[UploadFile, File(description="Front of the college ID card")],
    user: Annotated[Me, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> VerificationStatus:
    # Read one byte past the limit so the service can tell "too large" without reading it all.
    limit = settings.verification_photo_max_bytes + 1
    return await service.submit_id_card(
        session, user, await selfie.read(limit), await id_card.read(limit)
    )
