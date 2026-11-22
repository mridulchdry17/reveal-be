import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import repository
from src.auth.constants import VerificationMethod
from src.auth.exceptions import CollegeEmailTaken, NotCollegeAccount
from src.auth.google import GoogleIdentity
from src.auth.models import AuthSession, UserAccount
from src.auth.schemas import Me, SignInResponse
from src.config import settings
from src.exceptions import NotFound, Unauthenticated


async def sign_in_with_google(session: AsyncSession, identity: GoogleIdentity) -> SignInResponse:
    """Find or create the account for this Google identity and open a new session.

    Any Google account may sign in. Signing in with a college account also verifies you,
    unless another account already claimed that college email.
    """
    if not identity.email or not identity.email_verified:
        raise Unauthenticated("Google account has no verified email")

    user = await _upsert_user(session, identity)
    if user.verified_at is None and is_college_account(identity):
        await _claim_college_email(session, user, identity.email)
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


async def verify_college_email(
    session: AsyncSession, user_id: uuid.UUID, identity: GoogleIdentity
) -> Me:
    """Mark the signed-in user as a student, proven by a Google account on the college domain."""
    user = await repository.get_user(session, user_id)
    if user is None:
        raise Unauthenticated("Signed out or session expired")
    if user.verified_at is not None:
        # Verified fields never change once set (rule 7); asking again is harmless.
        return _to_me(user)
    if not is_college_account(identity):
        raise NotCollegeAccount(f"Pick your @{settings.college_domain} Google account")
    if not await _claim_college_email(session, user, identity.email):
        raise CollegeEmailTaken("That college email already verified another account")
    await session.commit()
    return _to_me(user)


async def mark_verified(
    session: AsyncSession, user_id: uuid.UUID, method: VerificationMethod
) -> bool:
    """Verify a student after an ID check or an admin's say-so. Doesn't commit.

    False if they were already verified: verified fields never change once set (rule 7).
    """
    user = await repository.get_user(session, user_id)
    if user is None:
        raise NotFound("No such account")
    if user.verified_at is not None:
        return False
    user.verified_via = method
    user.verified_at = datetime.now(UTC)
    await session.flush()
    return True


async def find_account(session: AsyncSession, email: str) -> Me | None:
    """The account that signs in with this Google email, or verified with this college email."""
    email = email.strip().lower()
    user = await repository.get_user_by_email(session, email)
    if user is None:
        user = await repository.get_user_by_college_email(session, email)
    return _to_me(user) if user else None


async def accounts(session: AsyncSession, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, Me]:
    return {u.id: _to_me(u) for u in await repository.get_users(session, user_ids)}


def is_college_account(identity: GoogleIdentity) -> bool:
    """Google says this account belongs to the college's Workspace, not personal Gmail.

    The "hd" claim is what proves it: anyone can put any address in a Gmail display name,
    but only the college's Workspace can issue tokens with its domain in "hd".
    """
    domain = settings.college_domain.lower()
    return (
        identity.email_verified
        and (identity.hosted_domain or "").lower() == domain
        and identity.email.endswith(f"@{domain}")
    )


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


async def _claim_college_email(session: AsyncSession, user: UserAccount, email: str) -> bool:
    """Verify `user` with this college email. False if another account already has it."""
    holder = await repository.get_user_by_college_email(session, email)
    if holder is not None and holder.id != user.id:
        return False
    try:
        # Savepoint: losing a race on the unique email must not undo the rest of the request.
        async with session.begin_nested():
            user.college_email = email
            user.verified_via = VerificationMethod.COLLEGE_EMAIL
            user.verified_at = datetime.now(UTC)
    except IntegrityError:
        await session.refresh(user)
        return False
    return True


def _to_me(user: UserAccount) -> Me:
    return Me(
        id=user.id,
        email=user.email,
        name=user.name,
        is_admin=is_admin(user.email),
        verified=user.verified_at is not None,
        verified_via=VerificationMethod(user.verified_via) if user.verified_via else None,
    )


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
