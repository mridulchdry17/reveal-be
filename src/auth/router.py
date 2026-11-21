from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import service
from src.auth.dependencies import (
    GoogleVerifier,
    bearer_token,
    current_user,
    get_google_verifier,
    limit_sign_ins,
)
from src.auth.schemas import CollegeEmailRequest, GoogleSignInRequest, Me, SignInResponse
from src.database import get_session
from src.schemas import ErrorResponse

router = APIRouter(prefix="/auth", tags=["auth"])

_UNAUTHENTICATED: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Not signed in"}
}


@router.post(
    "/google",
    response_model=SignInResponse,
    status_code=status.HTTP_200_OK,
    summary="Sign in with a Google credential",
    dependencies=[Depends(limit_sign_ins)],
    responses={
        401: {"model": ErrorResponse, "description": "Invalid Google credential"},
        429: {"model": ErrorResponse, "description": "Too many attempts"},
    },
)
async def sign_in_with_google(
    body: GoogleSignInRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    verify: Annotated[GoogleVerifier, Depends(get_google_verifier)],
) -> SignInResponse:
    identity = await verify(body.credential)
    return await service.sign_in_with_google(session, identity)


@router.get(
    "/me",
    response_model=Me,
    status_code=status.HTTP_200_OK,
    summary="The signed-in account",
    responses=_UNAUTHENTICATED,
)
async def me(user: Annotated[Me, Depends(current_user)]) -> Me:
    return user


@router.post(
    "/sign-out",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Sign this device out",
    responses=_UNAUTHENTICATED,
)
async def sign_out(
    token: Annotated[str, Depends(bearer_token)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    await service.sign_out(session, token)


@router.post(
    "/college-email",
    response_model=Me,
    status_code=status.HTTP_200_OK,
    summary="Verify as a student with a college Google account",
    dependencies=[Depends(limit_sign_ins)],
    responses={
        401: {"model": ErrorResponse, "description": "Not signed in, or invalid credential"},
        403: {"model": ErrorResponse, "description": "Not a college Google account"},
        409: {"model": ErrorResponse, "description": "College email verified another account"},
        429: {"model": ErrorResponse, "description": "Too many attempts"},
    },
)
async def verify_college_email(
    body: CollegeEmailRequest,
    user: Annotated[Me, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    verify: Annotated[GoogleVerifier, Depends(get_google_verifier)],
) -> Me:
    identity = await verify(body.credential)
    return await service.verify_college_email(session, user.id, identity)
