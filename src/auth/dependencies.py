from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import google, service
from src.auth.schemas import Me
from src.config import settings
from src.database import get_session
from src.exceptions import PermissionDenied, Unauthenticated
from src.security import RateLimiter, limit_by_ip

sign_in_limiter = RateLimiter(limit=settings.sign_ins_per_ip_per_hour, window_seconds=3600)
limit_sign_ins = limit_by_ip(sign_in_limiter)

GoogleVerifier = Callable[[str], Awaitable[google.GoogleIdentity]]


def get_google_verifier() -> GoogleVerifier:
    """Overridden in tests with a fake, so tests never call Google."""
    return google.verify_credential


_bearer = HTTPBearer(auto_error=False, description="Session token from POST /v1/auth/google")


async def bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    if credentials is None:
        raise Unauthenticated("Sign in first")
    return credentials.credentials


async def current_user(
    token: Annotated[str, Depends(bearer_token)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Me:
    return await service.user_for_token(session, token)


async def admin_user(user: Annotated[Me, Depends(current_user)]) -> Me:
    if not user.is_admin:
        raise PermissionDenied
    return user


async def verified_user(user: Annotated[Me, Depends(current_user)]) -> Me:
    """Signed in and a verified student. Every product endpoint uses this."""
    if not user.verified:
        raise PermissionDenied("Verify you're a student first")
    return user
