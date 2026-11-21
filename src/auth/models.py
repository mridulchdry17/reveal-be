import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Someone who signed in with Google. Being here does not mean they're a verified student."""

    # "user" is a reserved word in Postgres.
    __tablename__ = "user_account"

    # Google's stable account id ("sub"). Emails can change; this can't.
    google_sub: Mapped[str] = mapped_column(String(255), unique=True)
    # Stored lowercased; refreshed from Google on every sign-in.
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200))


class AuthSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A signed-in device. Deleting the row signs that device out."""

    __tablename__ = "auth_session"

    # SHA-256 of the bearer token; the token itself is never stored.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
