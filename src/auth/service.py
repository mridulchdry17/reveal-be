import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import repository
from src.auth.google import GoogleIdentity
from src.auth.models import AuthSession, UserAccount
from src.auth.schemas import Me, SignInResponse
from src.config import settings
from src.exceptions import Unauthenticated


async def sign_in_with_google(session: AsyncSession, identity: GoogleIdentity) -> SignInResponse:
    """Find or create the account for this Google identity and open a new session.

    Any Google account may sign in; proving you're an ADGIPS student is a separate step.
    """
    if not identity.email or not identity.email_verified:
        raise Unauthenticated("Google account has no verified email")

    user = await _upsert_user(session, identity)
    token = secrets.token_urlsafe(32)
    await repository.add(
        session,
        AuthSession(
            token_hash=_hash(token),
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(days=settings.session_days),
        ),
    )
    await session.commit()
    return SignInResponse(token=token, user=_to_me(user))


async def user_for_token(session: AsyncSession, token: str) -> Me:
    user = await repository.get_user_for_token(session, _hash(token), datetime.now(UTC))
    if user is None:
        raise Unauthenticated("Signed out or session expired")
    return _to_me(user)


async def sign_out(session: AsyncSession, token: str) -> None:
    await repository.delete_session(session, _hash(token))
    await session.commit()


def is_admin(email: str) -> bool:
    return email.lower() in {e.lower() for e in settings.admin_emails}


async def _upsert_user(session: AsyncSession, identity: GoogleIdentity) -> UserAccount:
    user = await repository.get_user_by_google_sub(session, identity.sub)
    if user is not None:
        user.email = identity.email
        user.name = identity.name
        await session.flush()
        return user
    user = UserAccount(google_sub=identity.sub, email=identity.email, name=identity.name)
    try:
        await repository.add(session, user)
    except IntegrityError:
        # Same account signing in on two devices at the same moment.
        await session.rollback()
        user = await repository.get_user_by_google_sub(session, identity.sub)
        if user is None:
            raise
    return user


def _to_me(user: UserAccount) -> Me:
    return Me(id=user.id, email=user.email, name=user.name, is_admin=is_admin(user.email))


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
