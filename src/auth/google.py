"""Checks a Google Identity Services credential (an ID token) and returns who it belongs to."""

from dataclasses import dataclass

from fastapi.concurrency import run_in_threadpool
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from src.config import settings
from src.exceptions import Unauthenticated

_transport = google_requests.Request()


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str
    email_verified: bool
    name: str
    # Google Workspace domain ("hd" claim), e.g. "adgips.ac.in". None for personal Gmail.
    hosted_domain: str | None


async def verify_credential(credential: str) -> GoogleIdentity:
    """Verify signature, audience (our client ID), issuer and expiry. Raises Unauthenticated."""
    if not settings.google_client_id:
        raise Unauthenticated("Google sign-in is not configured")
    try:
        # The library is synchronous (it may fetch Google's keys), so keep it off the event loop.
        claims = await run_in_threadpool(
            id_token.verify_oauth2_token, credential, _transport, settings.google_client_id
        )
    except ValueError as exc:
        raise Unauthenticated("Invalid Google credential") from exc
    return GoogleIdentity(
        sub=str(claims["sub"]),
        email=str(claims.get("email", "")).lower(),
        email_verified=bool(claims.get("email_verified", False)),
        name=str(claims.get("name") or claims.get("email", "")),
        hosted_domain=claims.get("hd"),
    )
